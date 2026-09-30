"""Offline deployment policy checks; never instantiate settings or read dotenv secrets."""

import os
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml
from voice_api.core.config import _ENV_FILES

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_KEYS = {"VITE_CLERK_PUBLISHABLE_KEY", "VITE_API_ORIGIN"}
PRIVATE_ENV = {
    "VOICE_DATABASE_URL",
    "VOICE_INTEGRATION_KEYS",
    "VOICE_INTEGRATION_ACTIVE_KEY",
    "VOICE_CALLBACK_SLOT_SIGNING_KEY",
    "VOICE_RUNTIME_SERVICE_TOKEN",
    "VOICE_PUBLIC_BASE_URL",
    "VOICE_CLERK_AUTHORIZED_PARTIES",
    "CLERK_SECRET_KEY",
    "CLERK_WEBHOOK_SIGNING_SECRET",
    "VOICE_GOOGLE_CALENDAR_CLIENT_ID",
    "VOICE_GOOGLE_CALENDAR_CLIENT_SECRET",
    "VOICE_GOOGLE_CALENDAR_REDIRECT_URI",
    "VOICE_CLOUDINARY_CLOUD_NAME",
    "VOICE_CLOUDINARY_API_KEY",
    "VOICE_CLOUDINARY_API_SECRET",
    "VOICE_SUPABASE_URL",
    "VOICE_SUPABASE_SERVICE_KEY",
}


def test_backend_dotenv_search_is_confined_to_api_directory():
    assert tuple(Path(path) for path in _ENV_FILES) == (
        ROOT / "apps/api/.env",
        ROOT / "apps/api/.env.local",
    )


def test_render_has_only_free_manual_web_service():
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text())
    assert set(blueprint) == {"services", "previews"}
    assert blueprint["previews"] == {"generation": "off"}
    assert len(blueprint["services"]) == 1
    service = blueprint["services"][0]
    assert service["type"] == "web"
    assert service["runtime"] == "docker"
    assert service["plan"] == "free"
    assert service["autoDeployTrigger"] == "off"
    assert service["healthCheckPath"] == "/health"
    assert service["dockerfilePath"] == "./Dockerfile"
    assert service["dockerContext"] == "."
    assert service["maxShutdownDelaySeconds"] == 300
    assert (
        not {
            "disk",
            "scaling",
            "numInstances",
            "preDeployCommand",
            "schedule",
            "startCommand",
            "dockerCommand",
            "previews",
        }
        & service.keys()
    )


def test_render_secrets_and_fail_closed_demo_defaults():
    service = yaml.safe_load((ROOT / "render.yaml").read_text())["services"][0]
    entries = service["envVars"]
    env = {item["key"]: item for item in entries}
    assert len(entries) == len(env), "Duplicate env entries can silently override admission"
    defaults = {
        "PORT": "10000",
        "VOICE_ENV": "production",
        "VOICE_DEBUG_DIAGNOSTICS": "false",
        "VOICE_HOSTED_CALLS_ENABLED": "false",
        "VOICE_MAX_CONCURRENT_CALLS": "1",
        "VOICE_CALL_MAX_DURATION_SECONDS": "600",
        "VOICE_ORGANIZATION_CREATION_ENABLED": "true",
        "VOICE_RECORDINGS_DIR": "/app/data/recordings",
        "VOICE_SUPABASE_PRIVATE_BUCKET": "voice-private",
    }
    assert env.keys() == PRIVATE_ENV | defaults.keys()
    for key, value in defaults.items():
        assert env[key] == {"key": key, "value": value}
    for key in PRIVATE_ENV:
        assert env[key] == {"key": key, "sync": False}
    # No provider keys, generated vault roots, automatic jobs or invented quota.
    assert not any("generateValue" in item for item in entries)
    assert "VOICE_RECORDING_QUOTA_BYTES" not in env


def test_docker_is_frozen_nonroot_single_owner_without_side_effect_startup():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert dockerfile.count("FROM python:3.12-slim-bookworm") == 2
    assert "ghcr.io/astral-sh/uv:0.9.17" in dockerfile
    assert "uv lock --check" in dockerfile
    assert dockerfile.count("uv sync --frozen --no-dev") == 2
    assert "--no-editable" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert all(lib in dockerfile for lib in ("ca-certificates", "libsndfile1", "libportaudio2"))
    command = next(line for line in dockerfile.splitlines() if line.startswith("CMD "))
    assert "exec uvicorn voice_api.main:app" in command
    assert "--host 0.0.0.0" in command and "${PORT:?PORT is required}" in command
    assert "--workers 1" in command
    assert "--timeout-graceful-shutdown 285" in command
    assert "--no-access-log" in command
    assert all(
        word not in command.lower() for word in ("alembic", "demo_call", "cron", "worker.py")
    )
    assert "COPY . ." not in dockerfile and "COPY . /app" not in dockerfile
    assert "ARG " not in dockerfile


def test_docker_context_is_default_deny_with_secret_exclusions():
    lines = [
        line
        for line in (ROOT / ".dockerignore").read_text().splitlines()
        if line and not line.startswith("#")
    ]
    assert lines[0] == "**"
    assert set(line for line in lines if line.startswith("!")) == {
        "!Dockerfile",
        "!.dockerignore",
        "!pyproject.toml",
        "!uv.lock",
        "!.python-version",
        "!apps/",
        "!apps/api/",
        "!apps/api/**",
        "!packages/",
        "!packages/voice_runtime/",
        "!packages/voice_runtime/**",
    }
    assert all(
        line in lines
        for line in (
            "**/.env",
            "**/.env.*",
            "**/.git",
            "**/.venv",
            "**/.pytest_*",
            ".pytest_*",
            "**/node_modules",
            "**/*.wav",
            "**/*.pem",
            "**/data",
        )
    )
    assert lines.index("**/.env.*") > lines.index("!packages/voice_runtime/**")


def test_netlify_is_static_spa_node24_without_sensitive_caching():
    config = tomllib.loads((ROOT / "netlify.toml").read_text())
    assert set(config) == {"build", "redirects", "headers"}
    assert config["build"] == {
        "base": "apps/dashboard",
        "publish": "dist",
        "command": "node ../../scripts/deploy/netlify-build.mjs",
        "environment": {
            "NODE_VERSION": "24",
            "NPM_FLAGS": "--package-lock=false --ignore-scripts",
        },
    }
    assert config["redirects"] == [
        {"from": "/*", "to": "/index.html", "status": 200, "force": False}
    ]
    headers = config["headers"][0]
    assert headers["for"] == "/*"
    assert headers["values"]["Cache-Control"] == "no-store"
    assert headers["values"]["Netlify-CDN-Cache-Control"] == "no-store"
    assert headers["values"]["Referrer-Policy"] == "no-referrer"


def test_frontend_env_example_keeps_only_public_build_configuration():
    env_file = ROOT / "apps/dashboard/.env.example"
    entries = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in env_file.read_text().splitlines()
        if line and not line.startswith("#")
    }
    assert set(entries) == PUBLIC_KEYS | {
        "VITE_DEBUG_PERF",
        "VITE_CLERK_SIGN_IN_URL",
        "VITE_CLERK_SIGN_UP_URL",
        "VITE_CLERK_AFTER_SIGN_IN_URL",
        "VITE_CLERK_AFTER_SIGN_UP_URL",
        "VITE_CLERK_ORGANIZATION_PROFILE_URL",
        "VITE_CLERK_CREATE_ORGANIZATION_URL",
        "VITE_CLERK_INVITATION_REDIRECT_URL",
    }
    assert entries["VITE_API_ORIGIN"] == "http://localhost:8000"
    assert entries["VITE_CLERK_PUBLISHABLE_KEY"].startswith("pk_test_")
    vite_config = (ROOT / "apps/dashboard/vite.config.ts").read_text()
    assert '"CLERK_PUBLISHABLE_KEY"' not in vite_config


def run_guard(tmp_path, overrides=None):
    node = shutil.which("node")
    assert node, "Node 24 is required to verify hosted public-build policy"
    env = {key: value for key, value in os.environ.items() if not key.startswith("VITE_")}
    env.update(
        VITE_CLERK_PUBLISHABLE_KEY="pk_test_synthetic", VITE_API_ORIGIN="https://api.example.test"
    )
    env.update(overrides or {})
    return subprocess.run(
        [node, str(ROOT / "scripts/deploy/netlify-build.mjs"), "--validate-only"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_public_build_guard_accepts_approved_public_configuration(tmp_path):
    result = run_guard(tmp_path)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "key",
    [
        "VITE_PROVIDER_KEY",
        "VITE_SUPABASE_SERVICE_KEY",
        "VITE_CLERK_SECRET_KEY",
        "VITE_RUNTIME_TOKEN",
    ],
)
def test_public_build_guard_rejects_unapproved_variables_without_echo(tmp_path, key):
    result = run_guard(tmp_path, {key: "synthetic-secret-must-not-appear"})
    assert result.returncode != 0
    assert "allowlist violated" in result.stderr
    assert "synthetic-secret-must-not-appear" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "origin",
    [
        "",
        "http://api.example.test",
        "https://api.example.test/api",
        "https://user:secret@api.example.test",
        "https://api.example.test/?key=x",
    ],
)
def test_public_build_guard_rejects_missing_or_unsafe_origin(tmp_path, origin):
    assert run_guard(tmp_path, {"VITE_API_ORIGIN": origin}).returncode != 0


@pytest.mark.parametrize(
    "filename", [".env", ".env.local", ".env.production", ".env.production.local"]
)
def test_public_build_guard_rejects_dotenv_without_reading_values(tmp_path, filename):
    (tmp_path / filename).write_text("VITE_SECRET=synthetic-value-must-not-appear")
    result = run_guard(tmp_path)
    assert result.returncode != 0
    assert "Dotenv files are forbidden" in result.stderr
    assert "synthetic-value-must-not-appear" not in result.stdout + result.stderr


def test_public_build_guard_rejects_secret_in_publishable_key_slot(tmp_path):
    result = run_guard(tmp_path, {"VITE_CLERK_PUBLISHABLE_KEY": "sk_test_synthetic"})
    assert result.returncode != 0
    assert "public Clerk publishable key" in result.stderr
