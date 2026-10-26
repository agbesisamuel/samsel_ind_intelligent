"""Verify the real broker/worker/local-mail reset path using only the reserved demo operator.

Creates one expiring synthetic reset proof, never consumes it or changes credentials.
It remains in the local mail sink for review. No token or email body is printed.
"""

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
django.setup()

from django.conf import settings  # noqa: E402

from sii.accounts.models import PasswordReset  # noqa: E402
from sii.accounts.security import token_digest  # noqa: E402
from sii.accounts.tasks import send_password_reset  # noqa: E402
from sii.tenants.management.commands.seed_demo import demo_id  # noqa: E402
from sii.tenants.models import Membership  # noqa: E402


def run():
    """Guard local fixture ownership, then require a digest matching real captured SMTP mail."""
    assert settings.ENVIRONMENT == "local"
    assert settings.EMAIL_HOST == "smtp" and settings.EMAIL_PORT == 1025
    assert settings.DATABASES["default"]["NAME"] == "sii_local"
    email = "operator@example.invalid"
    assert Membership.objects.filter(
        user_id=demo_id(email), user__email=email, organisation__is_demo=True
    ).exists(), "Run seed-demo first"
    before = set(PasswordReset.objects.filter(user_id=demo_id(email)).values_list("pk", flat=True))
    send_password_reset.delay(email)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        pending = PasswordReset.objects.filter(user_id=demo_id(email)).exclude(pk__in=before)
        if pending.exists():
            with urllib.request.urlopen("http://smtp:8025/api/v1/messages", timeout=3) as response:
                messages = json.load(response)["messages"]
            for item in messages:
                if not any(recipient.get("Address") == email for recipient in item.get("To", [])):
                    continue
                with urllib.request.urlopen(
                    "http://smtp:8025/api/v1/message/" + item["ID"], timeout=3
                ) as response:
                    body = json.load(response).get("Text", "")
                if "/reset#token=" in body:
                    token = body.split("#token=", 1)[1].strip()
                    if pending.filter(token_hash=token_digest(token)).exists():
                        print("PASS: queued reset delivered to local SMTP; stored proof is hashed")
                        return
        time.sleep(0.5)
    raise RuntimeError("Local account-mail round trip did not complete")


if __name__ == "__main__":
    try:
        run()
    except Exception:  # noqa: BLE001 — connection exceptions can contain secret-bearing mail.
        print("FAIL: local account-mail round trip; no credentials or message body logged")
        sys.exit(1)
