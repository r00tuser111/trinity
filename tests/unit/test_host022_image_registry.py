"""HOST-022 — configurable image namespace + Docker Hub publishing.

Hosted installs pull `${TRINITY_IMAGE_REGISTRY:-ghcr.io/abilityai}/<image>`,
so a fork's own Docker Hub builds are one `.env` line away. The publish
workflow pushes to Docker Hub when the DOCKERHUB_* secrets are set, and to
GHCR otherwise (or additionally, with PUBLISH_GHCR=true).

The shell is EXECUTED, not grepped: the start.sh functions and the workflow's
`Select registries` body run under bash with controlled inputs.

Pure stdlib + PyYAML + bash: no docker daemon, no network.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

pytestmark = pytest.mark.unit

if shutil.which("bash") is None:  # pragma: no cover
    pytest.skip("bash not available", allow_module_level=True)

_ROOT = Path(__file__).resolve().parents[2]
_START_SH = _ROOT / "scripts" / "deploy" / "start.sh"
_HOSTED = _ROOT / "docker-compose.hosted.yml"
_WORKFLOW = _ROOT / ".github" / "workflows" / "publish-images.yml"
_ENV_EXAMPLE = _ROOT / ".env.example"

_BUILT = ("trinity-backend", "trinity-frontend", "trinity-scheduler", "trinity-mcp-server")


# ---------------------------------------------------------------------------
# start.sh
# ---------------------------------------------------------------------------

def _function(name: str) -> str:
    text = _START_SH.read_text(encoding="utf-8")
    match = re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", text, re.S | re.M)
    assert match, f"start.sh no longer defines {name}()"
    return match.group(0)


def _resolve(tmp_path: Path, *, shell_value: str | None = None, env_file: str = "") -> subprocess.CompletedProcess:
    (tmp_path / ".env").write_text(env_file, encoding="utf-8")
    script = "\n".join([
        "set -euo pipefail",
        _function("env_value"),
        _function("resolve_image_registry"),
        _function("image_registry_host"),
        "resolve_image_registry",
        'printf "%s|%s" "$TRINITY_IMAGE_REGISTRY" "$(image_registry_host)"',
    ])
    env = {k: v for k, v in os.environ.items() if k != "TRINITY_IMAGE_REGISTRY"}
    if shell_value is not None:
        env["TRINITY_IMAGE_REGISTRY"] = shell_value
    return subprocess.run(["bash", "-c", script], cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=30)


def test_default_is_the_upstream_ghcr(tmp_path):
    out = _resolve(tmp_path)
    assert out.returncode == 0, out.stderr
    assert out.stdout == "ghcr.io/abilityai|ghcr.io"


def test_dockerhub_user_from_env_file(tmp_path):
    out = _resolve(tmp_path, env_file='TRINITY_IMAGE_REGISTRY="youruser"  # my builds\n')
    assert out.returncode == 0, out.stderr
    assert out.stdout == "youruser|Docker Hub"


def test_shell_value_beats_env_file_and_trailing_slash_is_trimmed(tmp_path):
    out = _resolve(tmp_path, shell_value="registry.example.com:5000/team/",
                   env_file="TRINITY_IMAGE_REGISTRY=youruser\n")
    assert out.returncode == 0, out.stderr
    assert out.stdout == "registry.example.com:5000/team|registry.example.com:5000"


def test_dockerhub_org_path_logs_in_to_docker_hub(tmp_path):
    out = _resolve(tmp_path, shell_value="yourorg/sub")
    assert out.stdout == "yourorg/sub|Docker Hub"


@pytest.mark.parametrize("bad", [
    "YourUser",                       # uppercase is rejected by docker locally
    "https://registry.example.com/x",  # scheme
    "youruser/trinity-backend:v1",     # tag
    "you user",
    "-leading",
])
def test_malformed_namespace_is_refused_before_any_pull(tmp_path, bad):
    out = _resolve(tmp_path, shell_value=bad)
    assert out.returncode == 1
    assert "TRINITY_IMAGE_REGISTRY" in out.stderr and "youruser" in out.stderr


def test_agent_base_pull_uses_the_configured_namespace():
    text = _START_SH.read_text(encoding="utf-8")
    assert '_base_remote="${TRINITY_IMAGE_REGISTRY}/trinity-agent-base:${TRINITY_IMAGE_TAG}"' in text
    # Resolved only for hosted runs, after the tag, before the first pull.
    resolved = text.index("    resolve_image_registry\n")
    assert text.index("\nresolve_image_tag\n") < resolved < text.index('_base_remote="')


def test_provision_persists_the_namespace():
    body = _function("provision_site")
    assert 'set_env_key TRINITY_IMAGE_REGISTRY "$TRINITY_IMAGE_REGISTRY"' in body


# ---------------------------------------------------------------------------
# compose + .env.example
# ---------------------------------------------------------------------------

def test_every_built_image_resolves_through_the_namespace():
    services = yaml.safe_load(_HOSTED.read_text(encoding="utf-8"))["services"]
    images = {svc.get("image", "") for svc in services.values()}
    for name in _BUILT:
        expected = f"${{TRINITY_IMAGE_REGISTRY:-ghcr.io/abilityai}}/{name}:${{TRINITY_IMAGE_TAG:-latest}}"
        assert expected in images, f"{name} does not resolve through TRINITY_IMAGE_REGISTRY"
    assert not any(i.startswith("ghcr.io/abilityai/") for i in images), "a hardcoded GHCR reference is left"


def test_env_example_documents_the_namespace():
    assert "TRINITY_IMAGE_REGISTRY" in _ENV_EXAMPLE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# publish-images.yml
# ---------------------------------------------------------------------------

def _steps() -> list[dict]:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["publish"]["steps"]


def _step(name: str) -> dict:
    for step in _steps():
        if step.get("name") == name or step.get("id") == name:
            return step
    raise AssertionError(f"no step {name!r}")


def _select(tmp_path: Path, **env: str) -> dict:
    out_file = tmp_path / "out"
    out_file.write_text("", encoding="utf-8")
    base = {"DH_USER": "", "DH_TOKEN": "", "DH_NAMESPACE": "", "PUBLISH_GHCR": "",
            "IMAGE_OWNER": "Abilityai", "IMAGE_NAME": "trinity-backend"}
    base.update(env)
    run_env = {"PATH": os.environ["PATH"], "GITHUB_OUTPUT": str(out_file), **base}
    proc = subprocess.run(["bash", "-c", _step("reg")["run"]], env=run_env,
                          capture_output=True, text=True, timeout=30)
    text = out_file.read_text(encoding="utf-8")
    outputs: dict = {"_rc": proc.returncode, "_stdout": proc.stdout}
    images = re.search(r"images<<TRINITY_EOF\n(.*?)TRINITY_EOF", text, re.S)
    outputs["images"] = images.group(1).split() if images else []
    for line in text.splitlines():
        if "=" in line and "<<" not in line:
            k, v = line.split("=", 1)
            outputs[k] = v
    return outputs


def test_no_dockerhub_secrets_keeps_ghcr_only(tmp_path):
    out = _select(tmp_path)
    assert out["_rc"] == 0
    assert out["dockerhub"] == "false" and out["ghcr"] == "true"
    assert out["images"] == ["ghcr.io/abilityai/trinity-backend"]


def test_dockerhub_secrets_publish_dockerhub_only(tmp_path):
    out = _select(tmp_path, DH_USER="YourUser", DH_TOKEN="dckr_pat_placeholder")
    assert out["_rc"] == 0
    assert out["dockerhub"] == "true" and out["ghcr"] == "false"
    assert out["images"] == ["docker.io/youruser/trinity-backend"]
    assert out["dockerhub_image"] == "docker.io/youruser/trinity-backend"
    assert "dckr_pat_placeholder" not in out["_stdout"]


def test_namespace_variable_and_publish_ghcr_add_up(tmp_path):
    out = _select(tmp_path, DH_USER="youruser", DH_TOKEN="t", DH_NAMESPACE="yourorg", PUBLISH_GHCR="true")
    assert out["images"] == ["docker.io/yourorg/trinity-backend", "ghcr.io/abilityai/trinity-backend"]


def test_half_configured_dockerhub_falls_back_to_ghcr(tmp_path):
    out = _select(tmp_path, DH_USER="youruser")
    assert out["dockerhub"] == "false" and out["images"] == ["ghcr.io/abilityai/trinity-backend"]


def test_invalid_namespace_fails_the_job(tmp_path):
    out = _select(tmp_path, DH_USER="youruser", DH_TOKEN="t", DH_NAMESPACE="bad/name")
    assert out["_rc"] == 1


def test_secrets_reach_the_shell_only_through_env():
    run = _step("reg")["run"]
    assert "${{" not in run, "secrets/vars must not be interpolated into the shell body"


def test_logins_and_tags_follow_the_selection():
    steps = _steps()
    logins = [s for s in steps if str(s.get("uses", "")).startswith("docker/login-action@")]
    conditions = sorted(s.get("if", "") for s in logins)
    assert conditions == ["steps.reg.outputs.dockerhub == 'true'", "steps.reg.outputs.ghcr == 'true'"]
    names = [s.get("name") or s.get("id") or s.get("uses") for s in steps]
    assert names.index("Select registries") < names.index("Log in to Docker Hub") < names.index("Derive image tags")
    assert _step("meta")["with"]["images"] == "${{ steps.reg.outputs.images }}"


def test_verification_runs_per_registry():
    assert _step("Verify anonymous pull")["if"] == "steps.reg.outputs.ghcr == 'true'"
    dh = _step("Verify anonymous Docker Hub pull")
    assert dh["if"] == "steps.reg.outputs.dockerhub == 'true'"
    assert "exit 1" not in dh["run"], "a private Docker Hub repository is a legitimate choice — warn, don't fail"
    assert "::warning" in dh["run"]
