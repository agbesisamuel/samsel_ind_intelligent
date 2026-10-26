"""Protect environment and reset boundaries before any domain fixtures are introduced."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

# The source mount and host checkout share the same repository-relative layout.
SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "dev.py"
spec = importlib.util.spec_from_file_location("dev", SCRIPT)
dev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dev)


@pytest.mark.parametrize("environment", ["production", "pilot", "staging", ""])
def test_settings_refuse_unapproved_environments(environment):
    """A new interpreter must reject every non-local/test deployment environment."""
    result = subprocess.run(
        [sys.executable, "-c", "import config.settings.base"],
        env={**os.environ, "SII_ENV": environment},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Only explicitly selected local/test" in result.stderr


@pytest.mark.parametrize("environment", ["production", "pilot", "staging", "test"])
def test_reset_guard_rejects_non_local_file(tmp_path, monkeypatch, environment):
    """Even confirmed reset cannot target a non-local configuration."""
    monkeypatch.setattr(dev, "ROOT", tmp_path)
    (tmp_path / ".env").write_text(
        f"SII_ENV={environment}\nPOSTGRES_DB=sii_local\nPOSTGRES_USER=sii_local\n"
    )
    with pytest.raises(SystemExit, match="Refusing operation"):
        dev.require_local()


def test_reset_guard_rejects_inherited_production_override(tmp_path, monkeypatch):
    """An inherited variable must not bypass an otherwise local .env file."""
    monkeypatch.setattr(dev, "ROOT", tmp_path)
    monkeypatch.setenv("SII_ENV", "production")
    (tmp_path / ".env").write_text(
        "SII_ENV=local\nPOSTGRES_DB=sii_local\nPOSTGRES_USER=sii_local\n"
    )
    with pytest.raises(SystemExit, match="Refusing operation"):
        dev.require_local()


def test_reset_requires_explicit_local_confirmation(tmp_path, monkeypatch):
    """The reset command fails before mutation unless its local guard is confirmed."""
    monkeypatch.setattr(dev, "ROOT", tmp_path)
    monkeypatch.setenv("SII_ENV", "local")
    monkeypatch.setattr(sys, "argv", ["dev.py", "reset-demo"])
    (tmp_path / ".env").write_text(
        "SII_ENV=local\nPOSTGRES_DB=sii_local\nPOSTGRES_USER=sii_local\n"
    )
    with pytest.raises(SystemExit, match="requires --confirm-local"):
        dev.main()


def test_setup_upgrade_preserves_credentials_and_is_idempotent(tmp_path, monkeypatch):
    """Adding S3 keys must never rotate existing service or legacy volume credentials."""
    monkeypatch.setattr(dev, "ROOT", tmp_path)
    monkeypatch.setenv("SII_ENV", "local")
    original = "SII_ENV=local\nPOSTGRES_DB=sii_local\nPOSTGRES_USER=sii_local\nLEGACY=keep"
    (tmp_path / ".env").write_text(original)
    (tmp_path / ".env.example").write_text(
        "SII_ENV=local\nS3_ACCESS_KEY=GENERATE_LOCALLY\nS3_SECRET_KEY=GENERATE_LOCALLY\n"
    )
    dev.setup()
    upgraded = (tmp_path / ".env").read_text()
    values = dev.environment_values()
    assert upgraded.startswith(original + "\n")
    assert values["LEGACY"] == "keep"
    for key in ["S3_ACCESS_KEY", "S3_SECRET_KEY"]:
        assert len(values[key]) == 64
        assert len(bytes.fromhex(values[key])) == 32
    assert values["S3_ACCESS_KEY"] != values["S3_SECRET_KEY"]
    dev.setup()
    assert (tmp_path / ".env").read_text() == upgraded


def test_setup_upgrade_refuses_nonlocal_without_writing(tmp_path, monkeypatch):
    """An upgrade cannot append secrets to a configuration outside the local boundary."""
    monkeypatch.setattr(dev, "ROOT", tmp_path)
    target = tmp_path / ".env"
    target.write_text("SII_ENV=production\n")
    with pytest.raises(SystemExit, match="Refusing operation"):
        dev.setup()
    assert target.read_text() == "SII_ENV=production\n"


@pytest.mark.parametrize("credential", ["", "GENERATE_LOCALLY", "short", '"bad-json'])
def test_storage_refuses_invalid_credentials_before_start(credential):
    """Storage must fail closed before creating config or opening anonymous listeners."""
    result = subprocess.run(
        ["sh", str(SCRIPT.with_name("storage-entrypoint.sh"))],
        env={**os.environ, "SII_ENV": "local", "S3_ACCESS_KEY": credential},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert result.stderr == "Run setup: invalid S3 credentials.\n"


def test_storage_refuses_nonlocal_environment():
    """The storage entrypoint enforces the local boundary even outside Compose."""
    result = subprocess.run(
        ["sh", str(SCRIPT.with_name("storage-entrypoint.sh"))],
        env={**os.environ, "SII_ENV": "production"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert result.stderr == "Object store requires local environment.\n"
