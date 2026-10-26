"""Prove encrypted S3 round-trip/checksum denial; clean only this unique synthetic object."""

import os
import sys
import uuid
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
django.setup()

from django.conf import settings  # noqa: E402

from sii.common import storage  # noqa: E402
from sii.tenants.management.commands.seed_demo import demo_id  # noqa: E402
from sii.tenants.models import Site  # noqa: E402


def run():
    """Use the private S3 proxy and real cryptography; never print keys, payloads or ciphertext."""
    assert settings.ENVIRONMENT == "local" and settings.DATABASES["default"]["NAME"] == "sii_local"
    site = Site.objects.get(pk=demo_id("A/site/1"), organisation__is_demo=True)
    identifier, body = uuid.uuid4(), b"SYNTHETIC encrypted external evidence\n"
    stored = False
    try:
        key, checksum = storage.put(site.organisation_id, site.pk, identifier, body)
        stored = True
        raw = storage.client().get_object(Bucket=storage.BUCKET, Key=key)["Body"]
        try:
            assert body not in raw.read()
        finally:
            raw.close()
        assert storage.get(site.organisation_id, site.pk, identifier, checksum) == body
        try:
            storage.get(site.organisation_id, site.pk, identifier, "0" * 64)
        except ValueError:
            pass
        else:
            raise AssertionError("Corrupt checksum accepted")
        print("PASS: encrypted private S3 round-trip, plaintext absence and checksum denial")
    finally:
        if stored:
            storage.discard(site.organisation_id, site.pk, identifier)


if __name__ == "__main__":
    try:
        run()
    except Exception:
        print("FAIL: encrypted local evidence check (details redacted)")
        raise SystemExit(1) from None
