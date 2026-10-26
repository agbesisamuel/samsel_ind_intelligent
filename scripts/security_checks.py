"""Verify local runtime privileges, audit checkpoints and actual API security headers."""

import importlib.metadata
import json
import os
import sys
import urllib.request
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
django.setup()

from django.conf import settings  # noqa: E402
from django.db import DatabaseError, connection, transaction  # noqa: E402

from sii.audit.verification import verify  # noqa: E402


def main():
    """Attempt forbidden DDL inside rollback-only transactions; never persist disabled guards."""
    assert settings.ENVIRONMENT == "local" and connection.settings_dict["USER"] == "sii_runtime"
    # These checks run inside the Linux API container, never against a host process.
    assert os.geteuid() != 0
    process_status = dict(
        line.split(":", 1)
        for line in Path("/proc/self/status").read_text().splitlines()
        if ":" in line
    )
    assert int(process_status["CapEff"].strip(), 16) == 0
    assert process_status["NoNewPrivs"].strip() == "1"
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user"
        )
        assert cursor.fetchone() == (False, False, False)
    denied = []
    for sql in [
        "ALTER TABLE audit_auditevent DISABLE TRIGGER USER",
        "CREATE TABLE public.sii_forbidden_probe (id integer)",
        "DELETE FROM django_migrations WHERE FALSE",
        # Catalog writes are migration-owner work, even if a statement matches no rows.
        "UPDATE billing_plan SET name=name WHERE FALSE",
    ]:
        refused = False
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(sql)
                transaction.set_rollback(True)
        except DatabaseError:
            refused = True
        assert refused, "Runtime privilege boundary failed"
        denied.append(True)
    with urllib.request.urlopen("http://api:8000/api/v1/health/", timeout=5) as response:
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert "default-src 'none'" in response.headers["Content-Security-Policy"]
        assert response.headers["Cache-Control"] == "no-store"
        assert "Access-Control-Allow-Origin" not in response.headers
    packages = []
    for distribution in importlib.metadata.distributions():
        metadata = distribution.metadata
        packages.append(
            {
                "name": metadata["Name"],
                "version": distribution.version,
                "license_expression": metadata.get("License-Expression"),
                "license": metadata.get("License", "Unknown")[:1000],
                "license_classifiers": [
                    c for c in metadata.get_all("Classifier", []) if c.startswith("License ::")
                ],
            }
        )
    Path("/tmp/sii-python-licenses.json").write_text(json.dumps(packages, indent=2))
    result = {
        "runtime_role": "sii_runtime",
        "forbidden_operations_denied": len(denied),
        "audit_checkpoints": verify(),
        "api_headers": "passed",
        "packages": len(packages),
        "non_root_no_capabilities": True,
    }
    Path("/tmp/sii-security-checks.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({key: value for key, value in result.items() if key != "audit_checkpoints"}))


if __name__ == "__main__":
    main()
