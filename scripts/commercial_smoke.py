"""Prove real local MFA, manual draft idempotency and owner CSV export without collections.

Creates only a disjoint fictional organisation/accounts, retains draft/audit history,
and disables both test identities on every exit. No customer IDs, addresses or
provider destinations can be supplied; secrets and MFA material never reach output.
"""

import os
import secrets
import sys
import uuid
from pathlib import Path

import django
import pyotp
import requests

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
django.setup()

from django.conf import settings  # noqa: E402
from django.db import connection, transaction  # noqa: E402
from django.utils import timezone  # noqa: E402

from sii.accounts.models import CustomUser  # noqa: E402
from sii.tenants.models import Membership, Organisation, RoleAssignment  # noqa: E402

ORIGIN = "http://api:8000"


def post(client, path, body=None):
    """Obtain fresh CSRF per mutation and retain cookies only in memory."""
    csrf = client.get(ORIGIN + "/api/v1/auth/csrf/", timeout=5).json()["csrf_token"]
    response = client.post(
        ORIGIN + path, json=body or {}, headers={"X-CSRFToken": csrf}, timeout=10
    )
    assert response.status_code in {200, 201}
    return response.json()


def login(user, password):
    """Complete genuine password/TOTP enrollment through the running HTTP service."""
    client = requests.Session()
    result = post(client, "/api/v1/auth/login/", {"email": user.email, "password": password})
    assert result["state"] == "enroll"
    seed = post(client, "/api/v1/auth/mfa/enroll/")["secret"]
    assert (
        post(client, "/api/v1/auth/mfa/verify/", {"code": pyotp.TOTP(seed).now()})["state"]
        == "complete"
    )
    return client


def main():
    """Export a synthetic zero-value draft; preserve monitoring and disable drill actors."""
    assert settings.ENVIRONMENT == "local" and connection.settings_dict["NAME"] == "sii_local"
    run = uuid.uuid4().hex
    password = secrets.token_urlsafe(32)
    with transaction.atomic():
        org = Organisation.objects.create(name="SYNTHETIC commercial drill " + run, is_demo=True)
        admin = CustomUser.objects.create_superuser(
            f"finance-{run}@example.invalid", password, verified_at=timezone.now()
        )
        owner = CustomUser.objects.create_user(
            f"owner-{run}@example.invalid", password, verified_at=timezone.now()
        )
        member = Membership.objects.create(organisation=org, user=owner)
        RoleAssignment.objects.create(organisation=org, membership=member, role="owner")
    try:
        with login(admin, password) as platform, login(owner, password) as customer:
            base = f"/api/v1/organisations/{org.pk}/"
            date = timezone.now().date().isoformat()
            body = {
                "reference": "SYNTHETIC-" + run[:12].upper(),
                "period_start": date,
                "period_end": date,
                "currency": "DKK",
                "net_amount": "0.00",
                "tax_amount": "0.00",
            }
            first = post(platform, base + "invoices/", body)
            assert post(platform, base + "invoices/", body)["id"] == first["id"]
            response = customer.get(ORIGIN + base + f"invoices/{first['id']}/export/", timeout=10)
            assert response.status_code == 200 and b"SYNTHETIC_FINANCE_DRAFT" in response.content
            status = customer.get(ORIGIN + base + "subscription/", timeout=10).json()
            assert not status["live_collections_enabled"] and not status["monitoring_suspended"]
            assert platform.get(ORIGIN + base + "sites/", timeout=10).status_code == 404
            print(
                f"PASS real MFA, idempotent draft, owner CSV; invoice={first['id']}; "
                "collections disabled"
            )
    finally:
        for user in [admin, owner]:
            user.is_active = False
            user.save(update_fields=["is_active"])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("FAIL commercial smoke (sensitive details redacted)", file=sys.stderr)
        raise SystemExit(1) from None
