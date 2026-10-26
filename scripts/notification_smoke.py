"""Exercise verified local capture and the dispatcher with reserved synthetic identities.

Consent proof is read only from the private Mailpit API and never printed. The drill
retains a disabled route and its attempts as evidence; it never creates an incident.
"""

import json
import os
import re
import sys
import time
import urllib.request
import uuid
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
django.setup()

from django.conf import settings  # noqa: E402
from django.utils import timezone  # noqa: E402

from sii.accounts.models import CustomUser  # noqa: E402
from sii.incidents.models import Incident  # noqa: E402
from sii.notifications import models, services  # noqa: E402
from sii.tenants.management.commands.seed_demo import demo_id  # noqa: E402
from sii.tenants.models import Site  # noqa: E402


def captured():
    """Read local capture metadata only; bodies and token material must not reach stdout."""
    with urllib.request.urlopen("http://smtp:8025/api/v1/messages", timeout=3) as response:
        return json.load(response)["messages"]


def run():
    """Verify opt-in through local mail, queue TEST and require exactly one captured message."""
    assert settings.ENVIRONMENT == "local" and settings.DATABASES["default"]["NAME"] == "sii_local"
    site = Site.objects.get(pk=demo_id("A/site/1"), organisation__is_demo=True)
    user = CustomUser.objects.get(pk=demo_id("operator@example.invalid"))
    contact = models.AlertContact.objects.filter(
        site=site, user=user, verified_at__isnull=False, disabled=False
    ).first()
    if not contact:
        contact = services.invite(site, user, user)
        for message in captured():
            if not any(
                recipient.get("Address") == user.email for recipient in message.get("To", [])
            ):
                continue
            with urllib.request.urlopen(
                "http://smtp:8025/api/v1/message/" + message["ID"], timeout=3
            ) as response:
                body = json.load(response).get("Text", "")
            proof = re.search(r"Proof: (\S+)", body)
            if str(contact.pk) in body and proof:
                services.confirm(contact, proof.group(1), user)
                break
        else:
            raise RuntimeError("No matching local consent capture")
    run_id = uuid.uuid4()
    route = models.AlertRoute.objects.create(
        organisation=site.organisation,
        site=site,
        name=f"TEST drill {run_id}",
        contact=contact,
        kinds=["too_warm"],
        severity="info",
        timezone=site.timezone,
        shift_start=0,
        shift_end=1440,
        created_by=user,
    )
    before = Incident.objects.filter(site=site).count()
    item = services.enqueue(route, contact, "test", timezone.now())
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            item.refresh_from_db()
            if item.status == "accepted":
                break
            time.sleep(0.5)
        assert item.status == "accepted" and item.history.count() == 1
        # Repeating the worker entry point must not send an already accepted intent.
        services.dispatch(item.pk)
        matches = [message for message in captured() if str(run_id) in message["Subject"]]
        assert len(matches) == 1 and matches[0]["Subject"].startswith("[TEST]")
        assert Incident.objects.filter(site=site).count() == before
        print(
            json.dumps(
                {
                    "result": "PASS",
                    "notification": str(item.pk),
                    "captures": 1,
                    "attempts": 1,
                    "new_incidents": 0,
                }
            )
        )
    finally:
        route.enabled = False
        route.save(update_fields=["enabled"])


if __name__ == "__main__":
    try:
        run()
    except Exception:
        print("FAIL: local notification drill; inspect scoped delivery evidence, not credentials.")
        raise SystemExit(1) from None
