"""Platform-wide model provider (LLM-PROVIDER-001).

One provider is active per instance. ``anthropic`` (the default) is the
behaviour Trinity has always had: agents get the platform ``ANTHROPIC_API_KEY``
and backend model calls go to api.anthropic.com. ``custom`` points both at an
Anthropic-compatible third party (e.g. DeepSeek's ``/anthropic`` endpoint).

Everything that asks "which endpoint, which key, which model" goes through this
module, so the two modes cannot disagree between the container env, the
backend's own calls and the selectable catalog.

The one rule the design rests on: in custom mode the Anthropic key must never
travel with a third-party base URL. `apply_platform_auth_env` therefore pops
``ANTHROPIC_API_KEY`` whenever it writes ``ANTHROPIC_BASE_URL``, and the agent
image force-unsets a `.env`-resident one (``execution_env``).
"""
from __future__ import annotations

import ipaddress
import json
import logging
import re
import socket
import time
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

MODE_KEY = "llm_provider_mode"
BASE_URL_KEY = "llm_base_url"
API_KEY_SETTING = "llm_api_key"
MODELS_KEY = "llm_models"
DEFAULT_MODEL_KEY = "llm_default_model"
FAST_MODEL_KEY = "llm_fast_model"

MODE_ANTHROPIC = "anthropic"
MODE_CUSTOM = "custom"
MODES = (MODE_ANTHROPIC, MODE_CUSTOM)

#: Settings the generic ``PUT /api/settings/{key}`` must refuse: the dedicated
#: route validates the URL and the model list, the generic one would not.
PROVIDER_SETTING_KEYS = frozenset({
    MODE_KEY, BASE_URL_KEY, MODELS_KEY, DEFAULT_MODEL_KEY, FAST_MODEL_KEY,
})

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

DEFAULT_CONTEXT_WINDOW = 128_000
_MIN_CONTEXT_WINDOW = 1_000
_MAX_CONTEXT_WINDOW = 10_000_000
_MAX_MODELS = 50
_MAX_URL_LEN = 2048

# A model id reaches the runtime as a `--model` argv element and is joined with
# commas into TRINITY_PROVIDER_MODELS, so: no leading `-`, no comma, no
# whitespace, bounded.
_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@\[\]\-]{0,127}$")

_METADATA_HOSTS = frozenset({
    "metadata", "metadata.google.internal", "metadata.goog",
    "instance-data", "instance-data.ec2.internal",
})

#: Container env this module owns. Stripped before every write so switching
#: back to Anthropic (or onto a subscription) leaves nothing behind.
PROVIDER_ENV_KEYS = (
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_SMALL_FAST_MODEL",
    "TRINITY_PROVIDER_MODELS",
    "TRINITY_PROVIDER_CONTEXT_WINDOWS",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
)


class ProviderConfigError(ValueError):
    """A provider setting that cannot be saved. The message is user-facing."""


@dataclass(frozen=True)
class ProviderModel:
    id: str
    label: str
    context_window: int

    def as_dict(self) -> dict:
        return {"id": self.id, "label": self.label, "context_window": self.context_window}


@dataclass(frozen=True)
class Provider:
    base_url: str
    api_key: str
    models: Tuple[ProviderModel, ...]
    default_model: str
    fast_model: str

    @property
    def model_ids(self) -> frozenset:
        return frozenset(m.id for m in self.models)

    def label_for(self, model_id: str) -> Optional[str]:
        for m in self.models:
            if m.id == model_id:
                return m.label
        return None

    def context_window_for(self, model_id: str) -> Optional[int]:
        for m in self.models:
            if m.id == model_id:
                return m.context_window
        return None


@dataclass(frozen=True)
class LlmEndpoint:
    """Where a backend-side Messages call goes. ``headers`` carries the key."""
    url: str
    headers: Dict[str, str]
    model: str
    provider: str


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

Resolver = Callable[[str], List[str]]


def _resolve_host(host: str) -> List[str]:
    try:
        return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})
    except (socket.gaierror, UnicodeError, OSError):
        return []


def _is_local(ip: ipaddress._BaseAddress) -> bool:
    return ip.is_loopback or ip.is_private


def validate_base_url(url: str, resolve: Resolver = _resolve_host) -> str:
    """Normalise and vet a provider base URL; raise ``ProviderConfigError``.

    https anywhere; http only to a loopback/private host (a local gateway such
    as LiteLLM, possibly a compose service name). Link-local and cloud-metadata
    hosts are refused outright: the backend sends the provider key there.
    """
    raw = (url or "").strip()
    if not raw:
        raise ProviderConfigError("Enter the provider's base URL.")
    if len(raw) > _MAX_URL_LEN:
        raise ProviderConfigError("The base URL is too long.")
    try:
        parsed = urlparse(raw)
    except ValueError:
        raise ProviderConfigError("The base URL is not a valid URL.")
    if "@" in parsed.netloc:
        raise ProviderConfigError("Remove the username or password from the URL — put the key in the API key field.")
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ProviderConfigError("The base URL must start with https:// and name a host.")
    if parsed.query or parsed.fragment:
        raise ProviderConfigError("The base URL cannot carry a query string or fragment.")

    host = parsed.hostname.lower().rstrip(".")
    if host in _METADATA_HOSTS:
        raise ProviderConfigError("That host is a cloud metadata service and cannot be used.")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        addresses = [ipaddress.ip_address(a.split("%", 1)[0]) for a in resolve(host)]

    if any(a.is_link_local or a.is_multicast or a.is_unspecified for a in addresses):
        raise ProviderConfigError("That host resolves to a link-local or reserved address and cannot be used.")
    if parsed.scheme == "http" and not (addresses and all(_is_local(a) for a in addresses)):
        raise ProviderConfigError("Use https:// — plain http:// is only allowed for a gateway on this machine or your private network.")

    return raw.rstrip("/")


def normalize_models(raw: Iterable) -> Tuple[ProviderModel, ...]:
    """Validate the model list. Labels default to the id; windows to 128K."""
    if not isinstance(raw, (list, tuple)):
        raise ProviderConfigError("Models must be a list.")
    models: List[ProviderModel] = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ProviderConfigError("Each model needs an id.")
        model_id = str(item.get("id") or "").strip()
        if not _MODEL_ID_RE.match(model_id):
            raise ProviderConfigError(
                f"'{model_id[:64]}' is not a usable model id — letters, digits and . _ - : / only, "
                "not starting with a dash."
            )
        if model_id in seen:
            raise ProviderConfigError(f"'{model_id}' is listed twice.")
        seen.add(model_id)
        label = str(item.get("label") or "").strip()[:80] or model_id
        window = item.get("context_window") or DEFAULT_CONTEXT_WINDOW
        try:
            window = int(window)
        except (TypeError, ValueError):
            raise ProviderConfigError(f"The context window for '{model_id}' must be a number.")
        if not _MIN_CONTEXT_WINDOW <= window <= _MAX_CONTEXT_WINDOW:
            raise ProviderConfigError(f"The context window for '{model_id}' is out of range.")
        models.append(ProviderModel(model_id, label, window))
    if not models:
        raise ProviderConfigError("Add at least one model.")
    if len(models) > _MAX_MODELS:
        raise ProviderConfigError(f"At most {_MAX_MODELS} models.")
    return tuple(models)


def _pick(model: Optional[str], models: Tuple[ProviderModel, ...], what: str) -> str:
    model = (model or "").strip()
    if not model:
        return models[0].id
    if model not in {m.id for m in models}:
        raise ProviderConfigError(f"The {what} model must be one of the listed models.")
    return model


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

_CACHE_TTL = 5.0
_cache: Optional[Tuple[float, Optional[Provider]]] = None


def invalidate_cache() -> None:
    global _cache
    _cache = None


def _settings():
    from services.settings_service import settings_service
    return settings_service


def _db():
    from database import db
    return db


def get_mode() -> str:
    mode = _settings().get_setting(MODE_KEY, MODE_ANTHROPIC) or MODE_ANTHROPIC
    return mode if mode in MODES else MODE_ANTHROPIC


def _stored_models() -> Tuple[ProviderModel, ...]:
    raw = _settings().get_setting(MODELS_KEY, "") or ""
    if not raw:
        return ()
    try:
        return normalize_models(json.loads(raw))
    except (ValueError, ProviderConfigError) as e:
        logger.warning("stored provider model list is unreadable: %s", e)
        return ()


def _load_provider() -> Optional[Provider]:
    if get_mode() != MODE_CUSTOM:
        return None
    s = _settings()
    base_url = s.get_setting(BASE_URL_KEY, "") or ""
    api_key = s._stored_secret_setting(API_KEY_SETTING)
    models = _stored_models()
    if not (base_url and api_key and models):
        # Never fall through silently to Anthropic without saying so.
        logger.warning("custom model provider is selected but incomplete or unreadable; using Anthropic")
        return None
    ids = {m.id for m in models}
    default = s.get_setting(DEFAULT_MODEL_KEY, "") or ""
    fast = s.get_setting(FAST_MODEL_KEY, "") or ""
    default = default if default in ids else models[0].id
    fast = fast if fast in ids else default
    return Provider(base_url, api_key, models, default, fast)


def get_active_provider(fresh: bool = False) -> Optional[Provider]:
    """The custom provider when custom mode is active and complete, else None.

    Cached for a few seconds (hot per-turn paths); ``fresh`` bypasses the cache
    for callers that must agree across uvicorn workers.
    """
    global _cache
    now = time.monotonic()
    if not fresh and _cache is not None and now - _cache[0] < _CACHE_TTL:
        return _cache[1]
    provider = _load_provider()
    _cache = (now, provider)
    return provider


def save_provider(
    *,
    base_url: str,
    models: Iterable,
    default_model: Optional[str],
    fast_model: Optional[str],
    api_key: Optional[str],
    resolve: Resolver = _resolve_host,
) -> None:
    """Validate and persist the custom provider, then switch to custom mode.

    A blank ``api_key`` keeps the stored one (the UI never receives it back).
    """
    url = validate_base_url(base_url, resolve)
    normalized = normalize_models(models)
    default = _pick(default_model, normalized, "default")
    fast = _pick(fast_model or default, normalized, "fast")
    s = _settings()
    key = (api_key or "").strip()
    if not key and not s._stored_secret_setting(API_KEY_SETTING):
        raise ProviderConfigError("Enter the provider's API key.")
    if "\n" in key or "\r" in key:
        raise ProviderConfigError("The API key cannot contain line breaks.")

    db = _db()
    if key:
        s.set_secret_setting(API_KEY_SETTING, key)
    db.set_setting(BASE_URL_KEY, url)
    db.set_setting(MODELS_KEY, json.dumps([m.as_dict() for m in normalized]))
    db.set_setting(DEFAULT_MODEL_KEY, default)
    db.set_setting(FAST_MODEL_KEY, fast)
    db.set_setting(MODE_KEY, MODE_CUSTOM)
    invalidate_cache()


def use_anthropic() -> None:
    """Switch back to Anthropic, keeping the custom provider for later."""
    _db().set_setting(MODE_KEY, MODE_ANTHROPIC)
    invalidate_cache()


def clear_provider() -> None:
    """Switch back to Anthropic and forget the custom provider, key included."""
    db = _db()
    for key in (BASE_URL_KEY, MODELS_KEY, DEFAULT_MODEL_KEY, FAST_MODEL_KEY):
        db.delete_setting(key)
    _settings().clear_secret_setting(API_KEY_SETTING)
    db.set_setting(MODE_KEY, MODE_ANTHROPIC)
    invalidate_cache()


def provider_status() -> dict:
    """The admin view. The key is reported as configured/masked, never returned."""
    s = _settings()
    models = _stored_models()
    key = s._stored_secret_setting(API_KEY_SETTING)
    return {
        "mode": get_mode(),
        "active": get_active_provider() is not None,
        "base_url": s.get_setting(BASE_URL_KEY, "") or "",
        "api_key_configured": bool(key),
        "api_key_masked": (key[:4] + "…" + key[-4:]) if len(key) > 12 else ("…" if key else ""),
        "models": [m.as_dict() for m in models],
        "default_model": s.get_setting(DEFAULT_MODEL_KEY, "") or "",
        "fast_model": s.get_setting(FAST_MODEL_KEY, "") or "",
    }


# ---------------------------------------------------------------------------
# Container env
# ---------------------------------------------------------------------------

def provider_env(provider: Provider) -> Dict[str, str]:
    return {
        "ANTHROPIC_BASE_URL": provider.base_url,
        "ANTHROPIC_AUTH_TOKEN": provider.api_key,
        "ANTHROPIC_MODEL": provider.default_model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": provider.default_model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": provider.default_model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": provider.fast_model,
        "ANTHROPIC_SMALL_FAST_MODEL": provider.fast_model,
        "TRINITY_PROVIDER_MODELS": ",".join(m.id for m in provider.models),
        "TRINITY_PROVIDER_CONTEXT_WINDOWS": ",".join(
            f"{m.id}={m.context_window}" for m in provider.models
        ),
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }


def strip_provider_env(env_vars: dict) -> None:
    for key in PROVIDER_ENV_KEYS:
        env_vars.pop(key, None)


def apply_provider_env(env_vars: dict) -> bool:
    """Write the custom provider's env (and drop the Anthropic key) if one is active.

    Returns False — with any stale provider env stripped — when Anthropic is
    in force, so the caller keeps its own Anthropic-key line unchanged.
    """
    strip_provider_env(env_vars)
    provider = get_active_provider()
    if provider is None:
        return False
    env_vars.pop("ANTHROPIC_API_KEY", None)
    env_vars.update(provider_env(provider))
    return True


def apply_platform_auth_env(env_vars: dict) -> None:
    """The "platform credential" branch for a Claude-runtime container."""
    from services.settings_service import get_anthropic_api_key

    if not apply_provider_env(env_vars):
        env_vars["ANTHROPIC_API_KEY"] = get_anthropic_api_key()


def platform_auth_env_matches(env_dict: dict) -> bool:
    """Does a container's env carry exactly what `apply_platform_auth_env` writes?"""
    desired: Dict[str, str] = {}
    apply_platform_auth_env(desired)
    return all(
        (env_dict.get(key) or "") == (desired.get(key) or "")
        for key in ("ANTHROPIC_API_KEY", *PROVIDER_ENV_KEYS)
    )


def has_provider_env(env_dict: dict) -> bool:
    return any(env_dict.get(key) for key in PROVIDER_ENV_KEYS)


# ---------------------------------------------------------------------------
# Backend-side model calls and the selectable catalog
# ---------------------------------------------------------------------------

def resolve_llm_endpoint(tier: str, anthropic_model: str) -> Optional[LlmEndpoint]:
    """The Messages endpoint for a backend call, or None when nothing is configured.

    ``tier`` is ``"fast"`` or ``"default"`` and only matters in custom mode;
    Anthropic mode keeps each caller's own model choice.
    """
    provider = get_active_provider()
    if provider is not None:
        model = provider.fast_model if tier == "fast" else provider.default_model
        return LlmEndpoint(
            url=f"{provider.base_url}/v1/messages",
            headers={
                "x-api-key": provider.api_key,
                "Authorization": f"Bearer {provider.api_key}",
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            model=model,
            provider=MODE_CUSTOM,
        )
    from services.settings_service import get_anthropic_api_key

    key = get_anthropic_api_key()
    if not key:
        return None
    return LlmEndpoint(
        url=ANTHROPIC_MESSAGES_URL,
        headers={
            "x-api-key": key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        model=anthropic_model,
        provider=MODE_ANTHROPIC,
    )


def provider_model_ids() -> frozenset:
    provider = get_active_provider()
    return provider.model_ids if provider else frozenset()


def stored_key_for(base_url: str) -> str:
    """The saved key, but only for the saved base URL — never re-aimed elsewhere."""
    s = _settings()
    stored_url = s.get_setting(BASE_URL_KEY, "") or ""
    if not stored_url or (base_url or "").strip().rstrip("/") != stored_url:
        return ""
    return s._stored_secret_setting(API_KEY_SETTING) or ""


def selectable_catalog() -> dict:
    """What every model picker offers right now."""
    provider = get_active_provider()
    if provider is None:
        return {"provider": MODE_ANTHROPIC, "models": None, "default_model": None, "fast_model": None}
    return {
        "provider": MODE_CUSTOM,
        "models": [m.as_dict() for m in provider.models],
        "default_model": provider.default_model,
        "fast_model": provider.fast_model,
    }


# ---------------------------------------------------------------------------
# Connectivity test and fleet convergence
# ---------------------------------------------------------------------------

_TEST_TIMEOUT_SECONDS = 20.0


async def check_provider(base_url: str, api_key: str, model: str, resolve: Resolver = _resolve_host) -> dict:
    """Send a one-token Messages call. Never raises; the key is never echoed."""
    import httpx

    try:
        url = validate_base_url(base_url, resolve)
    except ProviderConfigError as e:
        return {"valid": False, "error": str(e)}
    model = (model or "").strip()
    if not _MODEL_ID_RE.match(model):
        return {"valid": False, "error": "Choose a model to test with."}
    key = (api_key or "").strip() or _settings()._stored_secret_setting(API_KEY_SETTING)
    if not key:
        return {"valid": False, "error": "Enter the provider's API key."}

    try:
        # No redirects: a 3xx to an internal host would carry the key there.
        async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS, follow_redirects=False) as client:
            response = await client.post(
                f"{url}/v1/messages",
                headers={
                    "x-api-key": key,
                    "Authorization": f"Bearer {key}",
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json={"model": model, "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]},
            )
    except httpx.TimeoutException:
        return {"valid": False, "error": "The provider did not answer within 20 seconds."}
    except httpx.HTTPError as e:
        return {"valid": False, "error": f"Could not reach the provider ({type(e).__name__})."}

    if response.status_code == 200:
        return {"valid": True, "model": model}
    if response.status_code in (401, 403):
        return {"valid": False, "error": "The provider rejected the API key."}
    if response.status_code == 404:
        return {"valid": False, "error": "Not found — check that the base URL is the provider's Anthropic-compatible endpoint."}
    if 300 <= response.status_code < 400:
        return {"valid": False, "error": "The provider answered with a redirect — use the final URL."}
    detail = ""
    try:
        body = response.json()
        detail = str((body.get("error") or {}).get("message") or "")[:200]
    except (ValueError, AttributeError):
        pass
    return {"valid": False, "error": f"The provider answered {response.status_code}" + (f": {detail}" if detail else ".")}


def stale_claude_agents() -> List[str]:
    """Running, durable Claude agents whose auth env no longer matches. SYNCHRONOUS.

    Ephemeral ghosts are excluded: they are volume-less, and recreating one
    destroys its workspace (trinity-enterprise#69).
    """
    from database import db
    from services.agent_service.helpers import check_api_key_env_matches, is_claude_runtime
    from services.docker_service import agent_container_runtimes, agent_container_states, get_agent_container

    states = agent_container_states() or {}
    runtimes = agent_container_runtimes() or {}
    stale = []
    for name, state in sorted(states.items()):
        if state != "running" or not is_claude_runtime(runtimes.get(name)):
            continue
        try:
            info = db.get_agent_ephemeral_info(name)
            if info is None or info.get("is_ephemeral"):
                continue
            container = get_agent_container(name)
            if container is not None and not check_api_key_env_matches(container, name):
                stale.append(name)
        except Exception as e:  # noqa: BLE001 — one unreadable agent must not stop the rest
            logger.warning("could not check auth env for agent '%s': %s", name, e)
    return stale


async def restart_agents(names: List[str]) -> dict:
    """Recreate each agent onto the current provider env, one at a time.

    Same guards as the ent#582 credential restart: the per-agent switch lock,
    and never an agent with a running execution (it converges on next start).
    """
    import asyncio

    from database import db
    from services.subscription_auto_switch import _restart_agent, agent_switch_lock

    restarted, skipped = [], []
    for name in names:
        try:
            async with await agent_switch_lock(name):
                if await asyncio.to_thread(db.agent_has_running_execution, name):
                    skipped.append(name)
                    continue
                await _restart_agent(name)
                restarted.append(name)
        except Exception as e:  # noqa: BLE001
            logger.error("restart of '%s' onto the model provider failed: %s", name, e)
            skipped.append(name)
    logger.info("model provider applied: %d restarted, %d left for next start", len(restarted), len(skipped))
    return {"restarted": restarted, "skipped": skipped}
