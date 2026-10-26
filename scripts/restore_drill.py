"""Create an encrypted backup and restore to fresh, unexposed containers on an isolated network.

Only uniquely named drill containers/networks are removed in finally. No source
volumes, database records or evidence objects are deleted. Encrypted backup/results
remain in ignored .artifacts; environment keys must be retained separately.
"""

import base64
import hashlib
import json
import subprocess
import time
import uuid
from datetime import UTC, datetime

from dev import ROOT, require_local

POSTGRES = (
    "postgres:17.11-bookworm@sha256:"
    "3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826"
)


def run(*args, input=None):
    """Capture all outputs; never echo dump bytes, secrets or provider exception text."""
    result = subprocess.run(args, input=input, capture_output=True, cwd=ROOT, check=False)
    if result.returncode:
        raise RuntimeError("Isolated restore command failed")
    return result.stdout


def compose(*args, input=None):
    """Pin all source reads to the guarded local Compose project."""
    return run("docker", "compose", "-f", str(ROOT / "compose.yaml"), *args, input=input)


def main():
    """Measure checkpoint freshness, startup, restore and integrity verification time."""
    require_local()
    destination = ROOT / ".artifacts" / ("restore-" + uuid.uuid4().hex)
    destination.mkdir(parents=True)
    checkpoint = json.loads(
        compose("exec", "-T", "api", "python", "/workspace/scripts/backup_crypto.py", "checkpoint")
    )
    dump = compose(
        "exec",
        "-T",
        "postgres",
        "pg_dump",
        "-U",
        "sii_local",
        "-d",
        "sii_local",
        "-Fc",
        "--no-owner",
        "--no-privileges",
    )
    encrypted = compose(
        "exec",
        "-T",
        "api",
        "python",
        "/workspace/scripts/backup_crypto.py",
        "seal",
        input=json.dumps(
            {"checkpoint": checkpoint, "dump": base64.b64encode(dump).decode()}
        ).encode(),
    )
    backup = destination / "backup.fernet"
    backup.write_bytes(encrypted)
    del dump
    started = time.monotonic()
    simulated_failure = datetime.now(UTC)
    prefix = "sii-restore-" + uuid.uuid4().hex[:12]
    network, database, objects = prefix + "-net", prefix + "-db", prefix + "-s3"
    created = []
    try:
        run("docker", "network", "create", "--internal", network)
        created.append(network)
        run(
            "docker",
            "run",
            "-d",
            "--name",
            database,
            "--network",
            network,
            "--network-alias",
            "restore-db",
            "-e",
            "POSTGRES_USER=sii_local",
            "-e",
            "POSTGRES_DB=sii_restore",
            "-e",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            "--tmpfs",
            "/var/lib/postgresql/data:rw",
            POSTGRES,
        )
        created.append(database)
        run(
            "docker",
            "run",
            "-d",
            "--name",
            objects,
            "--network",
            network,
            "--network-alias",
            "object-store",
            "--env-file",
            str(ROOT / ".env"),
            "--tmpfs",
            "/data:uid=10001,gid=10001",
            "--tmpfs",
            "/tmp:mode=1777",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "sii-local-object-store-backend",
        )
        created.append(objects)
        deadline = time.monotonic() + 90
        while True:
            try:
                run(
                    "docker", "exec", database, "pg_isready", "-U", "sii_local", "-d", "sii_restore"
                )
                run("docker", "exec", objects, "sh", "/opt/sii/storage-probe.sh", "health")
                break
            except RuntimeError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(1)
        restored_dump = compose(
            "exec",
            "-T",
            "api",
            "python",
            "/workspace/scripts/backup_crypto.py",
            "dump",
            input=encrypted,
        )
        run(
            "docker",
            "exec",
            "-i",
            database,
            "pg_restore",
            "-U",
            "sii_local",
            "-d",
            "sii_restore",
            "--exit-on-error",
            "--no-owner",
            "--no-privileges",
            input=restored_dump,
        )
        del restored_dump
        verified = run(
            "docker",
            "run",
            "--rm",
            "-i",
            "--network",
            network,
            "--env-file",
            str(ROOT / ".env"),
            "-e",
            "POSTGRES_HOST=restore-db",
            "-e",
            "POSTGRES_DB=sii_restore",
            "-e",
            "SII_DB_RUNTIME=0",
            "-v",
            str(ROOT / "apps/api") + ":/workspace/apps/api:ro",
            "-v",
            str(ROOT / "scripts") + ":/workspace/scripts:ro",
            "sii-local-api",
            "python",
            "/workspace/scripts/backup_crypto.py",
            "verify",
            input=encrypted,
        )
        result = json.loads(verified)
        result.update(
            {
                "rto_sec": time.monotonic() - started,
                "observed_audit_rpo_sec": max(
                    0,
                    (
                        simulated_failure - datetime.fromisoformat(result["latest_audit_at"])
                    ).total_seconds(),
                ),
                "checkpoint_age_at_verification_sec": (
                    datetime.fromisoformat(result["verified_at"])
                    - datetime.fromisoformat(checkpoint["at"])
                ).total_seconds(),
                "backup_sha256": hashlib.sha256(encrypted).hexdigest(),
                "encrypted_bytes": len(encrypted),
                "isolated_network": True,
                "published_ports": 0,
                "rpo_scope": "Fresh manual snapshot; scheduled production RPO remains unproven",
            }
        )
        (destination / "result.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        print("Encrypted backup and results: " + str(destination))
    finally:
        for name in reversed(created[1:]):
            run("docker", "rm", "-f", name)
        if created:
            run("docker", "network", "rm", network)


if __name__ == "__main__":
    main()
