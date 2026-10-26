"""Cross-platform local-only developer commands shared by Make and CI.

Commands execute argument arrays without a shell. Setup generates unique secrets
in an ignored file and never prints them. No command deletes persistent volumes.
"""

import argparse
import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = [
    "docker",
    "compose",
    "--project-directory",
    str(ROOT),
    "-f",
    str(ROOT / "compose.yaml"),
]


def run(*args):
    """Run a local executable, surfacing failures immediately without secret output."""
    subprocess.run(list(args), cwd=ROOT, check=True)


def environment_values():
    """Read simple generated .env assignments; do not execute shell interpolation."""
    path = ROOT / ".env"
    if not path.exists():
        raise SystemExit("Run setup first.")
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if line and not line.startswith("#") and "=" in line
    )


def require_local():
    """Reject inherited overrides and files that could target a non-local dataset."""
    values = environment_values()
    for key, expected in {
        "SII_ENV": "local",
        "POSTGRES_DB": "sii_local",
        "POSTGRES_USER": "sii_local",
    }.items():
        if values.get(key) != expected or os.environ.get(key, expected) != expected:
            raise SystemExit(f"Refusing operation: {key} must be {expected}.")
    if os.environ.get("COMPOSE_FILE") or os.environ.get("COMPOSE_PROJECT_NAME"):
        raise SystemExit("Refusing Compose project/file overrides.")


def setup():
    """Create secrets or append missing template keys without rotating existing values.

    Upgrades retain legacy keys and volume credentials for manual recovery. Existing
    files must pass the local guard before any write; values never reach stdout.
    """
    target = ROOT / ".env"
    if target.exists():
        require_local()
        values = environment_values()
        missing = []
        for line in (ROOT / ".env.example").read_text().splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key not in values:
                if value == "GENERATE_LOCALLY":
                    value = secrets.token_hex(32)
                missing.append(f"{key}={value}")
        if missing:
            with target.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write("\n" + "\n".join(missing) + "\n")
        print("Existing local values preserved; missing template keys added if needed.")
        return
    lines = []
    for line in (ROOT / ".env.example").read_text().splitlines():
        if line.endswith("=GENERATE_LOCALLY"):
            line = line.split("=", 1)[0] + "=" + secrets.token_hex(32)
        lines.append(line)
    # Exclusive creation avoids replacing secrets when setup processes race.
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines) + "\n")
    if os.name != "nt":
        target.chmod(0o600)
    print("Created local .env. Run up to build and start the stack.")


def compose(*args):
    """Execute only this project's explicit Compose file after the local guard."""
    require_local()
    run(*COMPOSE, *args)


def main():
    """Dispatch documented development operations; propagate every failing exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "setup",
            "up",
            "down",
            "migrate",
            "seed-demo",
            "reset-demo",
            "test",
            "lint",
            "build",
            "contracts",
            "smoke",
            "auth-smoke",
            "telemetry-smoke",
            "notification-smoke",
            "evidence-smoke",
            "report-smoke",
            "security-check",
            "restore-drill",
            "reference-load",
            "container-audit",
            "adapter-smoke",
            "commercial-smoke",
            "audit",
            "secret-scan",
            "e2e",
        ],
    )
    parser.add_argument("--confirm-local", action="store_true")
    args = parser.parse_args()
    match args.command:
        case "setup":
            setup()
        case "up":
            compose("up", "--build", "-d", "--wait", "--wait-timeout", "300")
        case "down":
            compose("down", "--remove-orphans")
        case "migrate":
            compose("run", "--rm", "migrate")
        case "seed-demo":
            compose("exec", "-T", "api", "python", "manage.py", "seed_demo")
        case "reset-demo":
            require_local()
            if args.command == "reset-demo" and not args.confirm_local:
                raise SystemExit(
                    "Reset requires --confirm-local; only synthetic fixture cleanup is permitted."
                )
            print(
                "Reset preserves identities and append-only audit evidence. No records deleted; "
                "seed-demo is idempotent. Use a separately scoped fixture reset in later sprints."
            )
        case "test":
            compose("exec", "-T", "-e", "SII_ENV=test", "api", "pytest")
            compose("exec", "-T", "web", "npm", "test")
        case "lint":
            compose(
                "exec",
                "-T",
                "api",
                "ruff",
                "check",
                "--no-cache",
                "--config",
                "pyproject.toml",
                ".",
                "/workspace/scripts",
            )
            compose(
                "exec",
                "-T",
                "api",
                "ruff",
                "format",
                "--check",
                "--no-cache",
                "--config",
                "pyproject.toml",
                ".",
                "/workspace/scripts",
            )
            compose("exec", "-T", "api", "python", "manage.py", "check")
            compose(
                "exec",
                "-T",
                "api",
                "python",
                "manage.py",
                "makemigrations",
                "--check",
                "--dry-run",
            )
            compose("exec", "-T", "web", "npm", "run", "lint")
            compose("exec", "-T", "web", "npm", "run", "typecheck")
        case "build":
            compose("build")
            compose("run", "--rm", "--no-deps", "web", "npm", "run", "build")
        case "contracts":
            # Generate into a container-owned location, then copy as the host user.
            # Linux bind mounts may not be writable by the non-root API UID.
            compose(
                "exec",
                "-T",
                "api",
                "python",
                "manage.py",
                "spectacular",
                "--file",
                "/tmp/sii-openapi.yaml",
                "--validate",
                "--fail-on-warn",
            )
            compose("cp", "api:/tmp/sii-openapi.yaml", "packages/api-contracts/openapi.yaml")
            compose(
                "exec",
                "-T",
                "api",
                "python",
                "manage.py",
                "spectacular",
                "--urlconf",
                "config.device_urls",
                "--file",
                "/tmp/sii-device.yaml",
                "--validate",
                "--fail-on-warn",
            )
            compose("cp", "api:/tmp/sii-device.yaml", "packages/api-contracts/device-openapi.yaml")
            # Generate as the non-root web user; host-side copy owns the bind-mounted
            # artifact, avoiding UID assumptions on Linux/Windows checkout permissions.
            compose("exec", "-T", "web", "npm", "run", "contracts:container")
            compose("cp", "web:/tmp/sii-schema.d.ts", "packages/api-contracts/schema.d.ts")
        case "smoke":
            compose("exec", "-T", "api", "python", "/workspace/scripts/stack_smoke.py")
            compose(
                "exec", "-T", "object-store-backend", "sh", "/opt/sii/storage-probe.sh", "smoke"
            )
        case "auth-smoke":
            compose("exec", "-T", "api", "python", "/workspace/scripts/auth_smoke.py")
        case "telemetry-smoke":
            compose(
                "exec",
                "-T",
                "device-api",
                "python",
                "manage.py",
                "simulate_gateway",
                "--count",
                "1000",
            )
        case "notification-smoke":
            compose("exec", "-T", "api", "python", "/workspace/scripts/notification_smoke.py")
        case "evidence-smoke":
            compose("exec", "-T", "api", "python", "/workspace/scripts/evidence_smoke.py")
        case "report-smoke":
            compose("exec", "-T", "api", "python", "/workspace/scripts/report_smoke.py")
        case "security-check":
            compose("exec", "-T", "api", "python", "/workspace/scripts/security_checks.py")
            compose(
                "exec", "-T", "api", "python", "/workspace/scripts/backup_crypto.py", "selftest"
            )
        case "restore-drill":
            run(sys.executable, "scripts/restore_drill.py")
        case "container-audit":
            run(sys.executable, "scripts/container_audit.py")
        case "adapter-smoke":
            compose("exec", "-T", "device-api", "python", "manage.py", "adapter_smoke")
        case "commercial-smoke":
            compose("exec", "-T", "api", "python", "/workspace/scripts/commercial_smoke.py")
        case "reference-load":
            compose("exec", "-T", "device-api", "python", "manage.py", "reference_load")
        case "audit":
            # pip-compile includes every transitive pin/hash. Scan those exact entries
            # directly; re-resolving/installing a temporary environment is unnecessary.
            compose(
                "exec",
                "-T",
                "api",
                "pip-audit",
                "--no-deps",
                "--disable-pip",
                "--progress-spinner",
                "off",
                "-r",
                "requirements.lock",
            )
            compose("exec", "-T", "web", "npm", "run", "audit")
        case "secret-scan":
            run(sys.executable, "scripts/scan_secrets.py")
        case "e2e":
            executable = "npm.cmd" if os.name == "nt" else "npm"
            run(executable, "--prefix", "apps/web", "run", "e2e")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
