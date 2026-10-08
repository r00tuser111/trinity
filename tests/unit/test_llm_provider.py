"""LLM-PROVIDER-001 — platform-wide custom model provider.

Pins the properties the feature rests on:

* the base URL refuses metadata / link-local hosts, embedded credentials and
  plain http to a public host;
* the provider key is stored encrypted and never returned unmasked;
* a Claude container in custom mode carries the provider env and NEVER the
  Anthropic key; switching back strips every provider variable;
* the start-path drift check sees a provider change;
* model validation, the platform default and the Workspace allow-list follow
  the provider;
* backend model calls resolve to the provider's endpoint.

Throwaway SQLite from the unit conftest — no network, no Docker.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import os
import types

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("cryptography")

os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "ab" * 32)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

pytestmark = pytest.mark.unit

_KEY = "sk-provider-test-0123456789"
_MODELS = [
    {"id": "deepseek-chat", "label": "DeepSeek Chat", "context_window": 128000},
    {"id": "deepseek-reasoner", "label": "DeepSeek Reasoner"},
]


def _live(name):
    return importlib.import_module(name)


def _lp():
    return _live("services.llm_provider")


def _public(host):
    return ["104.18.0.1"]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    db = _live("database").db
    secret = _live("services.secret_settings")

    def purge():
        lp = _lp()
        for key in lp.PROVIDER_SETTING_KEYS:
            db.delete_setting(key)
        db.delete_setting(lp.API_KEY_SETTING)
        db.delete_setting(secret.encrypted_key_for(lp.API_KEY_SETTING))
        db.delete_setting("anthropic_api_key")
        db.delete_setting(secret.encrypted_key_for("anthropic_api_key"))
        lp.invalidate_cache()

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    purge()
    yield
    purge()


def _save(**overrides):
    args = dict(base_url="https://api.deepseek.com/anthropic", models=_MODELS,
                default_model="deepseek-chat", fast_model=None, api_key=_KEY,
                resolve=_public)
    args.update(overrides)
    _lp().save_provider(**args)


# ---------------------------------------------------------------------------
# URL safety
# ---------------------------------------------------------------------------

class TestBaseUrl:
    def test_https_public_host_is_accepted_and_trailing_slash_trimmed(self):
        assert _lp().validate_base_url("https://api.deepseek.com/anthropic/", _public) == \
            "https://api.deepseek.com/anthropic"

    @pytest.mark.parametrize("url", [
        "http://169.254.169.254/latest",
        "https://metadata.google.internal/x",
        "https://[fe80::1]/v1",
    ])
    def test_metadata_and_link_local_are_refused(self, url):
        with pytest.raises(_lp().ProviderConfigError):
            _lp().validate_base_url(url, _public)

    def test_hostname_resolving_to_link_local_is_refused(self):
        with pytest.raises(_lp().ProviderConfigError):
            _lp().validate_base_url("https://sneaky.example.com", lambda h: ["169.254.169.254"])

    def test_plain_http_only_for_private_or_loopback(self):
        lp = _lp()
        assert lp.validate_base_url("http://litellm:4000", lambda h: ["172.18.0.5"]) == "http://litellm:4000"
        assert lp.validate_base_url("http://127.0.0.1:4000", _public) == "http://127.0.0.1:4000"
        with pytest.raises(lp.ProviderConfigError):
            lp.validate_base_url("http://api.deepseek.com/anthropic", _public)
        with pytest.raises(lp.ProviderConfigError):
            lp.validate_base_url("http://unresolvable.invalid", lambda h: [])

    @pytest.mark.parametrize("url", [
        "https://user:pass@api.deepseek.com/anthropic",
        "https://api.deepseek.com/anthropic?x=1",
        "ftp://api.deepseek.com",
        "",
    ])
    def test_malformed_urls_are_refused(self, url):
        with pytest.raises(_lp().ProviderConfigError):
            _lp().validate_base_url(url, _public)


class TestModels:
    @pytest.mark.parametrize("bad", ["-rf", "a,b", "has space", ""])
    def test_ids_that_could_smuggle_argv_or_break_the_env_list_are_refused(self, bad):
        with pytest.raises(_lp().ProviderConfigError):
            _lp().normalize_models([{"id": bad}])

    def test_duplicates_and_empty_lists_are_refused(self):
        lp = _lp()
        with pytest.raises(lp.ProviderConfigError):
            lp.normalize_models([{"id": "a"}, {"id": "a"}])
        with pytest.raises(lp.ProviderConfigError):
            lp.normalize_models([])

    def test_label_and_context_window_default(self):
        (m,) = _lp().normalize_models([{"id": "deepseek-chat"}])
        assert (m.label, m.context_window) == ("deepseek-chat", _lp().DEFAULT_CONTEXT_WINDOW)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_anthropic_mode_by_default(self):
        assert _lp().get_active_provider() is None
        assert _lp().get_mode() == "anthropic"

    def test_save_activates_and_stores_the_key_encrypted(self):
        db = _live("database").db
        secret = _live("services.secret_settings")
        _save()
        provider = _lp().get_active_provider()
        assert provider.base_url == "https://api.deepseek.com/anthropic"
        assert provider.default_model == "deepseek-chat"
        assert provider.fast_model == "deepseek-chat"
        assert provider.api_key == _KEY
        assert db.get_setting_value("llm_api_key", None) is None
        envelope = db.get_setting_value(secret.encrypted_key_for("llm_api_key"), None)
        assert envelope and _KEY not in envelope

    def test_status_masks_the_key(self):
        _save()
        status = _lp().provider_status()
        assert status["mode"] == "custom" and status["active"] is True
        assert _KEY not in json.dumps(status)
        assert status["api_key_configured"] is True

    def test_blank_key_keeps_the_stored_one_and_no_key_at_all_is_refused(self):
        lp = _lp()
        with pytest.raises(lp.ProviderConfigError):
            _save(api_key="")
        _save()
        _save(api_key="", default_model="deepseek-reasoner")
        assert lp.get_active_provider().api_key == _KEY
        assert lp.get_active_provider().default_model == "deepseek-reasoner"

    def test_stored_key_is_reused_only_for_the_stored_base_url(self):
        lp = _lp()
        assert lp.stored_key_for("https://api.deepseek.com/anthropic") == ""
        _save()
        assert lp.stored_key_for("https://api.deepseek.com/anthropic/") == _KEY
        assert lp.stored_key_for("https://elsewhere.example.com/anthropic") == ""
        assert lp.stored_key_for("") == ""

    def test_default_model_must_be_listed(self):
        with pytest.raises(_lp().ProviderConfigError):
            _save(default_model="claude-sonnet-4-6")

    def test_use_anthropic_keeps_config_and_clear_forgets_it(self):
        lp = _lp()
        _save()
        lp.use_anthropic()
        assert lp.get_active_provider() is None
        assert lp.provider_status()["base_url"]
        lp.clear_provider()
        status = lp.provider_status()
        assert status["base_url"] == "" and status["api_key_configured"] is False


# ---------------------------------------------------------------------------
# Container env
# ---------------------------------------------------------------------------

class TestContainerEnv:
    def test_anthropic_mode_injects_the_platform_key_and_strips_provider_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api-platform")
        env = {"ANTHROPIC_BASE_URL": "https://old", "TRINITY_PROVIDER_MODELS": "x"}
        _lp().apply_platform_auth_env(env)
        assert env == {"ANTHROPIC_API_KEY": "sk-ant-api-platform"}

    def test_custom_mode_never_carries_the_anthropic_key(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api-platform")
        _save()
        env = {"ANTHROPIC_API_KEY": "sk-ant-api-platform"}
        _lp().apply_platform_auth_env(env)
        assert "ANTHROPIC_API_KEY" not in env
        assert env["ANTHROPIC_BASE_URL"] == "https://api.deepseek.com/anthropic"
        assert env["ANTHROPIC_AUTH_TOKEN"] == _KEY
        assert env["ANTHROPIC_MODEL"] == "deepseek-chat"
        assert env["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "deepseek-chat"
        assert env["TRINITY_PROVIDER_MODELS"] == "deepseek-chat,deepseek-reasoner"
        assert env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "1"

    def test_env_match_detects_a_provider_change(self):
        lp = _lp()
        _save()
        env = {}
        lp.apply_platform_auth_env(env)
        assert lp.platform_auth_env_matches(env)
        _save(default_model="deepseek-reasoner")
        assert not lp.platform_auth_env_matches(env)


def _container(env):
    return types.SimpleNamespace(attrs={"Config": {"Env": [f"{k}={v}" for k, v in env.items()]}})


class TestDriftCheck:
    @pytest.fixture
    def helpers(self, monkeypatch):
        mod = _live("services.agent_service.helpers")
        state = {"sub": None, "platform": True}
        monkeypatch.setattr(mod.db, "get_agent_subscription_id", lambda n: state["sub"])
        monkeypatch.setattr(mod.db, "get_use_platform_api_key", lambda n: state["platform"])
        monkeypatch.setattr(mod.db, "get_subscription_token", lambda s: "oat-token")
        mod._state = state
        return mod

    def test_claude_container_with_the_anthropic_key_is_stale_in_custom_mode(self, helpers, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api-platform")
        old = {"AGENT_RUNTIME": "claude-code", "ANTHROPIC_API_KEY": "sk-ant-api-platform"}
        assert helpers.check_api_key_env_matches(_container(old), "a")
        _save()
        assert not helpers.check_api_key_env_matches(_container(old), "a")
        fresh = {"AGENT_RUNTIME": "claude-code"}
        _lp().apply_platform_auth_env(fresh)
        assert helpers.check_api_key_env_matches(_container(fresh), "a")

    def test_non_claude_runtime_keeps_comparing_the_bare_key(self, helpers, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api-platform")
        _save()
        gemini = {"AGENT_RUNTIME": "gemini-cli", "ANTHROPIC_API_KEY": "sk-ant-api-platform"}
        assert helpers.check_api_key_env_matches(_container(gemini), "a")

    def test_subscription_with_leftover_provider_env_is_stale(self, helpers):
        helpers._state["sub"] = "sub-1"
        env = {"AGENT_RUNTIME": "claude-code", "CLAUDE_CODE_OAUTH_TOKEN": "oat-token",
               "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic"}
        assert not helpers.check_api_key_env_matches(_container(env), "a")


# ---------------------------------------------------------------------------
# Models follow the provider
# ---------------------------------------------------------------------------

class TestModelSelection:
    def test_platform_default_and_public_channel_follow_the_provider(self):
        ss = _live("services.settings_service")
        assert ss.is_valid_public_channel_model("claude-sonnet-4-6")
        _save()
        assert ss.get_platform_default_model() == "deepseek-chat"
        assert ss.is_valid_public_channel_model("deepseek-reasoner")
        assert not ss.is_valid_public_channel_model("claude-sonnet-4-6")

    def test_dispatch_gate_accepts_provider_ids_by_exact_match_only(self):
        mc = _live("services.model_catalog")
        ids = frozenset({"deepseek-chat"})
        assert mc.validate_dispatch_model("deepseek-chat", ids) == "deepseek-chat"
        with pytest.raises(mc.InvalidModelError):
            mc.validate_dispatch_model("deepseek-chat")
        with pytest.raises(mc.InvalidModelError):
            mc.validate_dispatch_model("deepseek-chat-x", ids)
        assert mc.validate_dispatch_model("sonnet", ids) == "sonnet"

    def test_workspace_offers_and_accepts_provider_models(self):
        svc = _live("client_portal.service")
        _save()
        options = svc.workspace_model_options()
        assert [o.id for o in options] == ["deepseek-chat", "deepseek-reasoner"]
        # The Workspace drops options without a tier, so a provider model must carry one.
        assert all(o.tier for o in options)
        assert svc.catalog_label("deepseek-reasoner") == "DeepSeek Reasoner"
        assert svc.validate_requested_model("deepseek-chat", is_platform=True) == "deepseek-chat"
        with pytest.raises(svc.ClientPortalError):
            svc.validate_requested_model("claude-haiku-4-5-20251001", is_platform=True)

    def test_catalog_is_null_for_anthropic_and_the_provider_list_otherwise(self):
        lp = _lp()
        assert lp.selectable_catalog()["models"] is None
        _save()
        cat = lp.selectable_catalog()
        assert [m["id"] for m in cat["models"]] == ["deepseek-chat", "deepseek-reasoner"]
        assert cat["default_model"] == "deepseek-chat"


# ---------------------------------------------------------------------------
# Backend model calls and auth flags
# ---------------------------------------------------------------------------

class TestBackendCalls:
    def test_endpoint_is_anthropic_with_the_callers_model_by_default(self, monkeypatch):
        lp = _lp()
        assert lp.resolve_llm_endpoint("fast", "claude-haiku-4-5-20251001") is None
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api-platform")
        ep = lp.resolve_llm_endpoint("fast", "claude-haiku-4-5-20251001")
        assert ep.url == "https://api.anthropic.com/v1/messages"
        assert ep.model == "claude-haiku-4-5-20251001"
        assert ep.headers["x-api-key"] == "sk-ant-api-platform"

    def test_endpoint_follows_the_provider_and_never_sends_the_anthropic_key(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api-platform")
        _save(fast_model="deepseek-reasoner")
        ep = _lp().resolve_llm_endpoint("fast", "claude-haiku-4-5-20251001")
        assert ep.url == "https://api.deepseek.com/anthropic/v1/messages"
        assert ep.model == "deepseek-reasoner"
        assert "sk-ant-api-platform" not in json.dumps(ep.headers)
        assert _lp().resolve_llm_endpoint("default", "x").model == "deepseek-chat"

    def test_compatibility_checks_run_against_the_provider(self, monkeypatch):
        ai = _live("services.compatibility.ai_checks")
        spec = _live("services.compatibility.spec")
        seen = {}

        async def fake_call(client, endpoint, checks, bundle):
            seen["endpoint"] = endpoint
            return {}

        monkeypatch.setattr(ai, "_call_category", fake_call)
        monkeypatch.setattr(ai, "get_anthropic_api_key", lambda: "")
        _save()
        asyncio.run(ai.run_ai({"files": {}}, list(spec.AI_IDS)[:1]))
        assert seen["endpoint"].model == "deepseek-chat"
        assert seen["endpoint"].url.startswith("https://api.deepseek.com/")

    def test_a_provider_counts_as_configured_auth(self):
        subs = _live("services.subscription_service")
        assert subs.instance_has_api_key() is False
        _save()
        assert subs.instance_has_api_key() is True
        assert subs.is_claude_auth_configured() is True


class _FakeResponse:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body = body or {}

    def json(self):
        return self._body


def _fake_client(response, seen):
    class _Client:
        def __init__(self, *a, **kw):
            seen["kwargs"] = kw

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            seen.update(url=url, headers=headers, json=json)
            return response
    return _Client


class TestCheckProvider:
    def test_success_sends_one_token_without_following_redirects(self, monkeypatch):
        import httpx
        seen = {}
        monkeypatch.setattr(httpx, "AsyncClient", _fake_client(_FakeResponse(200), seen))
        out = asyncio.run(_lp().check_provider("https://api.deepseek.com/anthropic", _KEY,
                                               "deepseek-chat", _public))
        assert out == {"valid": True, "model": "deepseek-chat"}
        assert seen["url"] == "https://api.deepseek.com/anthropic/v1/messages"
        assert seen["json"]["max_tokens"] == 1
        assert seen["kwargs"]["follow_redirects"] is False

    def test_rejected_key_and_bad_url_are_named_without_echoing_the_key(self, monkeypatch):
        import httpx
        monkeypatch.setattr(httpx, "AsyncClient", _fake_client(_FakeResponse(401), {}))
        out = asyncio.run(_lp().check_provider("https://api.deepseek.com/anthropic", _KEY,
                                               "deepseek-chat", _public))
        assert out["valid"] is False and _KEY not in out["error"]
        out = asyncio.run(_lp().check_provider("http://169.254.169.254", _KEY, "m", _public))
        assert out["valid"] is False


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def _client(role="admin"):
    sr = _live("routers.settings")
    app = FastAPI()
    app.include_router(sr.router)
    user = types.SimpleNamespace(
        id=1, username=role, email=f"{role}@example.com", role=role,
        agent_name=None, connector_agent=None, mcp_scope=None,
    )
    # Keyed on the objects the routes actually captured: other harnesses
    # re-import `dependencies`, so a fresh lookup can be a different function.
    for mod in ("routers.settings.model_provider", "routers.settings.generic"):
        app.dependency_overrides[_live(mod).get_current_user] = lambda: user
    return TestClient(app)


class TestRoutes:
    @pytest.fixture(autouse=True)
    def _quiet(self, monkeypatch):
        async def _noop(*a, **kw):
            return None
        audit = _live("services.platform_audit_service").platform_audit_service
        monkeypatch.setattr(audit, "log", _noop)
        monkeypatch.setattr(_lp(), "_resolve_host", _public)
        monkeypatch.setattr(_live("routers.settings.model_provider"), "_connect_waiting_agents", lambda: None)

    def _body(self, **kw):
        body = {"mode": "custom", "base_url": "https://api.deepseek.com/anthropic",
                "api_key": _KEY, "models": _MODELS, "default_model": "deepseek-chat"}
        body.update(kw)
        return body

    def test_admin_can_save_read_and_switch_back(self):
        c = _client()
        r = c.put("/api/settings/model-provider", json=self._body())
        assert r.status_code == 200, r.text
        assert r.json()["mode"] == "custom" and _KEY not in r.text
        assert c.get("/api/settings/model-catalog").json()["default_model"] == "deepseek-chat"
        r = c.put("/api/settings/model-provider", json={"mode": "anthropic"})
        assert r.json()["mode"] == "anthropic"

    def test_bad_url_is_a_400_naming_the_problem(self):
        r = _client().put("/api/settings/model-provider",
                          json=self._body(base_url="http://169.254.169.254"))
        assert r.status_code == 400

    def test_non_admin_cannot_read_or_write_but_can_read_the_catalog(self):
        c = _client("user")
        assert c.get("/api/settings/model-provider").status_code == 403
        assert c.put("/api/settings/model-provider", json=self._body()).status_code == 403
        assert c.get("/api/settings/model-catalog").status_code == 200

    def test_generic_put_cannot_bypass_the_validated_route(self):
        r = _client().put("/api/settings/llm_base_url", json={"value": "http://169.254.169.254"})
        assert r.status_code == 422

    def test_keyless_test_uses_the_stored_key_only_against_the_stored_url(self, monkeypatch):
        seen = []

        async def _check(base_url, api_key, model, *a):
            seen.append((base_url, api_key))
            return {"valid": bool(api_key)}

        monkeypatch.setattr(_lp(), "check_provider", _check)
        c = _client()
        c.put("/api/settings/model-provider", json=self._body())
        body = {"base_url": "https://api.deepseek.com/anthropic", "model": "deepseek-chat"}
        assert c.post("/api/settings/model-provider/test", json=body).json()["valid"] is True
        body["base_url"] = "https://elsewhere.example.com/anthropic"
        assert c.post("/api/settings/model-provider/test", json=body).json()["valid"] is False
        assert seen == [("https://api.deepseek.com/anthropic", _KEY),
                        ("https://elsewhere.example.com/anthropic", "")]
