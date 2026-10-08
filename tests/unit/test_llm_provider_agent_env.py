"""LLM-PROVIDER-001 — the agent-image half of the custom model provider.

The backend bakes ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN /
TRINITY_PROVIDER_MODELS into a Claude container's env. Inside the image:

  - `arm_provider_auth_guard` force-unsets a `.env` ANTHROPIC_API_KEY (it must
    never ride along to a third-party base URL) and pins the routing pair to
    the boot baseline;
  - `cli_model_arg` drops a `--model` the provider does not serve, so the
    provider's ANTHROPIC_MODEL default applies instead;
  - `PUT /api/model` accepts provider model ids.

execution_env is loaded standalone by path, matching test_2114.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import os
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

_ROOT = Path(__file__).resolve().parents[2]
_AGENT = _ROOT / "docker" / "base-image" / "agent_server"
_MODULE = _AGENT / "services" / "execution_env.py"

pytestmark = pytest.mark.unit

_PROVIDER_BASELINE = {
    "AGENT_RUNTIME": "claude-code",
    "ANTHROPIC_BASE_URL": "https://provider.example.com/anthropic",
    "ANTHROPIC_AUTH_TOKEN": "provider-token",
    "ANTHROPIC_MODEL": "deepseek-chat",
    "TRINITY_PROVIDER_MODELS": "deepseek-chat, deepseek-reasoner",
    "TRINITY_PROVIDER_CONTEXT_WINDOWS": "deepseek-chat=64000,deepseek-reasoner=128000",
}

_CONTROLLED_KEYS = tuple(_PROVIDER_BASELINE) + ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")


@pytest.fixture(autouse=True)
def _isolate_environ():
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)


def _load(baseline: dict):
    spec = importlib.util.spec_from_file_location(
        f"_execution_env_provider_{len(sys.modules)}", _MODULE
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.INITIAL_ENV = dict(baseline)
    for key in _CONTROLLED_KEYS:
        if key in baseline:
            os.environ[key] = baseline[key]
        else:
            os.environ.pop(key, None)
    return mod


@pytest.fixture
def env_file(tmp_path):
    return tmp_path / ".env"


class TestGuard:

    def test_env_api_key_never_reaches_provider_spawn(self, env_file):
        mod = _load(_PROVIDER_BASELINE)
        assert mod.arm_provider_auth_guard() is True
        env_file.write_text('ANTHROPIC_API_KEY="sk-ant-api-stale"\n')

        env = mod.build_execution_env(env_file=env_file)

        assert "ANTHROPIC_API_KEY" not in env
        assert env["ANTHROPIC_AUTH_TOKEN"] == "provider-token"
        assert env["ANTHROPIC_BASE_URL"] == _PROVIDER_BASELINE["ANTHROPIC_BASE_URL"]

    def test_env_cannot_reroute_the_provider_token(self, env_file):
        mod = _load(_PROVIDER_BASELINE)
        mod.arm_provider_auth_guard()
        env_file.write_text(
            'ANTHROPIC_BASE_URL="https://elsewhere.example.net"\n'
            'ANTHROPIC_AUTH_TOKEN="other"\n'
        )

        env = mod.build_execution_env(env_file=env_file)

        assert env["ANTHROPIC_BASE_URL"] == _PROVIDER_BASELINE["ANTHROPIC_BASE_URL"]
        assert env["ANTHROPIC_AUTH_TOKEN"] == "provider-token"

    @pytest.mark.parametrize("baseline", [
        {},
        {"ANTHROPIC_API_KEY": "sk-ant-api-real"},
        {"ANTHROPIC_BASE_URL": "https://provider.example.com"},  # no token
        {**_PROVIDER_BASELINE, "AGENT_RUNTIME": "gemini-cli"},
    ])
    def test_does_not_arm_without_a_claude_provider_baseline(self, env_file, baseline):
        mod = _load(baseline)
        assert mod.arm_provider_auth_guard() is False
        env_file.write_text('ANTHROPIC_API_KEY="sk-ant-api-own"\n')

        env = mod.build_execution_env(env_file=env_file)

        assert env["ANTHROPIC_API_KEY"] == "sk-ant-api-own"
        assert mod.provider_models() == ()


class TestModelArg:

    def test_provider_models_parsed_from_baseline(self):
        mod = _load(_PROVIDER_BASELINE)
        assert mod.provider_models() == ("deepseek-chat", "deepseek-reasoner")

    def test_env_file_cannot_widen_the_model_list(self):
        mod = _load({k: v for k, v in _PROVIDER_BASELINE.items() if k != "TRINITY_PROVIDER_MODELS"})
        os.environ["TRINITY_PROVIDER_MODELS"] = "claude-opus-4-1"
        assert mod.provider_models() == ()

    @pytest.mark.parametrize("model,expected", [
        ("deepseek-reasoner", "deepseek-reasoner"),
        ("sonnet", "sonnet"),            # remapped via ANTHROPIC_DEFAULT_SONNET_MODEL
        ("claude-sonnet-4-6", None),     # safety-net default: provider default instead
        ("fable", None),                 # no provider remap for this alias
        ("sonnet[1m]", None),
        (None, None),
        ("", None),
    ])
    def test_provider_mode_filters_unserved_models(self, model, expected):
        mod = _load(_PROVIDER_BASELINE)
        assert mod.cli_model_arg(model) == expected

    @pytest.mark.parametrize("model", ["claude-sonnet-4-6", "fable", "sonnet[1m]"])
    def test_anthropic_mode_passes_models_through(self, model):
        mod = _load({"AGENT_RUNTIME": "claude-code"})
        assert mod.cli_model_arg(model) == model

    def test_context_window_from_provider(self):
        mod = _load(_PROVIDER_BASELINE)
        assert mod.provider_context_window("deepseek-chat") == 64000
        assert mod.provider_context_window("deepseek-reasoner") == 128000
        assert mod.provider_context_window("unknown") is None
        assert mod.provider_context_window(None) is None

    def test_no_context_window_without_provider(self):
        mod = _load({"TRINITY_PROVIDER_CONTEXT_WINDOWS": "deepseek-chat=64000"})
        assert mod.provider_context_window("deepseek-chat") is None


class TestWiring:

    @staticmethod
    def _model_flag_sources(path: Path) -> list:
        """Source of every expression passed after a literal "--model"."""
        tree = ast.parse(path.read_text())
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.List) and len(node.elts) == 2:
                first = node.elts[0]
                if isinstance(first, ast.Constant) and first.value == "--model":
                    found.append(ast.unparse(node.elts[1]))
        return found

    @pytest.mark.parametrize("rel", ["services/claude_code.py", "services/headless_executor.py"])
    def test_model_flag_goes_through_cli_model_arg(self, rel):
        path = _AGENT / rel
        sources = self._model_flag_sources(path)
        assert sources == ["model_arg"], sources
        assert "model_arg = cli_model_arg(" in path.read_text()

    def test_guard_is_armed_at_boot(self):
        tree = ast.parse((_AGENT / "main.py").read_text())
        calls = [
            stmt.value.func.id for stmt in tree.body
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Name)
        ]
        assert "arm_provider_auth_guard" in calls


class TestSetModelEndpoint:

    @pytest.fixture
    def chat(self, monkeypatch):
        from agent_server.routers import chat as chat_router
        from agent_server.state import agent_state
        monkeypatch.setattr(agent_state, "agent_runtime", "claude-code")
        monkeypatch.setattr(agent_state, "current_model", None)
        return chat_router, agent_state

    def _put(self, chat_router, model):
        from agent_server.models import ModelRequest
        return asyncio.run(chat_router.set_model(ModelRequest(model=model)))

    def test_accepts_provider_model(self, chat, monkeypatch):
        chat_router, state = chat
        monkeypatch.setattr(chat_router, "provider_models", lambda: ("deepseek-chat",))
        assert self._put(chat_router, "deepseek-chat")["model"] == "deepseek-chat"
        assert state.current_model == "deepseek-chat"

    def test_rejects_unknown_model_without_provider(self, chat, monkeypatch):
        chat_router, _ = chat
        monkeypatch.setattr(chat_router, "provider_models", lambda: ())
        with pytest.raises(HTTPException) as exc:
            self._put(chat_router, "deepseek-chat")
        assert exc.value.status_code == 400

    def test_get_lists_provider_models(self, chat, monkeypatch):
        chat_router, _ = chat
        monkeypatch.setattr(chat_router, "provider_models", lambda: ("deepseek-chat",))
        body = asyncio.run(chat_router.get_model())
        assert body["available_models"] == ["deepseek-chat"]
