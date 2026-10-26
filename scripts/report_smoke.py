"""Exercise independent report worker and encrypted S3 with reserved synthetic scope only."""

import hashlib
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
django.setup()

from django.conf import settings  # noqa: E402
from django.utils import timezone  # noqa: E402

from sii.accounts.models import CustomUser  # noqa: E402
from sii.common import storage  # noqa: E402
from sii.reports.services import download, grant, request_report  # noqa: E402
from sii.tenants.management.commands.seed_demo import demo_id  # noqa: E402
from sii.tenants.models import Site  # noqa: E402


def run():
    """Keep durable job evidence; write only a synthetic PDF sample to container scratch for QA."""
    assert settings.ENVIRONMENT == "local" and settings.DATABASES["default"]["NAME"] == "sii_local"
    site = Site.objects.get(pk=demo_id("A/site/1"), organisation__is_demo=True)
    user = CustomUser.objects.get(email="owner-a@example.invalid")
    now = timezone.now()
    for format in ["pdf", "csv"]:
        job = request_report(
            user,
            site,
            {"start": now - timedelta(minutes=5), "end": now, "format": format, "locale": "en"},
        )
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            job.refresh_from_db()
            if job.status in {"ready", "failed"}:
                break
            time.sleep(1)
        assert job.status == "ready", job.error_code
        body = download(job, user, grant(job, user).pk)
        assert hashlib.sha256(body).hexdigest() == job.checksum
        stream = storage.client().get_object(
            Bucket=storage.BUCKET, Key=storage.key_for(job.organisation_id, job.site_id, job.pk)
        )["Body"]
        try:
            assert body not in stream.read()
        finally:
            stream.close()
        if format == "pdf":
            assert body.startswith(b"%PDF-")
            Path("/tmp/sii-report-sample.pdf").write_bytes(body)
        print(f"PASS {format}: worker, encrypted artifact, checksum, scoped grant; job={job.pk}")


if __name__ == "__main__":
    try:
        run()
    except Exception:
        print("FAIL: local synthetic report drill (details redacted)")
        raise SystemExit(1) from None
