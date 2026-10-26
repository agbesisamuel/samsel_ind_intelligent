"""Durable ingestion rejects tenant/device spoofing and preserves evidence through retries."""

import secrets
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from test_assets import endpoint, inventory  # noqa: F401
from test_identity_tenancy import post

from sii.assets.models import CalibrationRecord, SensorCommissioning
from sii.telemetry.models import DeviceCredential, ProcessingOutbox, Reading, Rejection
from sii.telemetry.security import cipher, provision, revoke
from sii.telemetry.services import ingest
from sii.telemetry.transport import process_reading

pytestmark = pytest.mark.django_db


@pytest.fixture
def qualified(inventory, settings):  # noqa: F811 - imported pytest fixture
    """Explicitly qualify a fictional sensor; no fixture claims real calibration or go-live."""
    settings.DEVICE_ENCRYPTION_KEY = secrets.token_hex(32)
    a = inventory["a"]
    sensor, gateway = a["sensor"], a["gateway"]
    sensor.state, gateway.state = "commissioning", "commissioning"
    gateway.save()
    sensor.engineering_min, sensor.engineering_max = -100, 150
    sensor.capability_reference = "Synthetic test profile only"
    sensor.save()
    scope = {
        "organisation": a["organisation"],
        "site": a["site"],
        "sensor": sensor,
        "recorded_by": inventory["world"]["a"]["user"],
    }
    CalibrationRecord.objects.create(
        **scope,
        reference="SYNTHETIC",
        checked_at=timezone.now() - timedelta(days=1),
        due_at=timezone.now() + timedelta(days=1),
    )
    SensorCommissioning.objects.create(
        **scope,
        technician_reference="SYNTHETIC",
        placement_reference="SYNTHETIC",
        read_only_scope=True,
    )
    secret = secrets.token_urlsafe(32)
    credential = DeviceCredential.objects.create(
        organisation=a["organisation"],
        site=a["site"],
        gateway=gateway,
        encrypted_secret=cipher().encrypt(secret.encode()).decode(),
        provisioned=True,
        expires_at=timezone.now() + timedelta(days=1),
    )
    return {**inventory, "credential": credential, "secret": secret}


def event(qualified, **changes):
    """Produce a valid deterministic-shape wire event; overrides exercise a single boundary."""
    return {
        "version": 1,
        "event_id": str(uuid.uuid4()),
        "sensor_id": str(qualified["a"]["sensor"].pk),
        "sequence": 1,
        "observed_at": timezone.now().isoformat(),
        "value": "0",
        "unit": "degC",
        **changes,
    }


def test_durable_duplicate_and_out_of_order(qualified):
    """Duplicate storms create one row/outbox; lower unique sequences retain both timestamps."""
    payload = event(qualified, sequence=10)
    first = ingest(qualified["credential"], payload, "https")
    for _ in range(20):
        assert ingest(qualified["credential"], payload, "mqtt")["status"] == "duplicate"
    assert Reading.objects.count() == ProcessingOutbox.objects.count() == 1
    assert Reading.objects.get().value == 0
    assert first["reading_id"] == str(Reading.objects.get().pk)
    older = event(
        qualified, sequence=9, observed_at=(timezone.now() - timedelta(hours=1)).isoformat()
    )
    assert ingest(qualified["credential"], older, "mqtt")["status"] == "accepted"
    assert "late_backfill" in Reading.objects.get(sequence=9).quality
    assert Reading.objects.get(sequence=9).received_at > Reading.objects.get(sequence=9).observed_at


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"organisation": str(uuid.uuid4())}, "invalid_contract"),
        ({"unit": "F"}, "invalid_contract"),
        ({"value": "NaN"}, "invalid_contract"),
        ({"value": "151"}, "engineering_range"),
        ({"sequence": -1}, "invalid_contract"),
        ({"observed_at": "2026-10-25T02:30:00"}, "invalid_contract"),
        ({"observed_at": "2000-01-01T00:00:00Z"}, "timestamp_window"),
    ],
)
def test_contract_quarantine(qualified, changes, reason):
    """Malformed/unit/range/skew input records only a reason/hash and never a usable reading."""
    assert ingest(qualified["credential"], event(qualified, **changes), "https")["reason"] == reason
    assert Reading.objects.count() == 0
    assert Rejection.objects.get().reason == reason


def test_foreign_and_same_org_other_site_rejected(qualified):
    """Possessing one gateway secret grants neither another tenant nor another site sensor."""
    for target in ["a2", "b"]:
        assert (
            ingest(
                qualified["credential"],
                event(qualified, sensor_id=str(qualified[target]["sensor"].pk)),
                "mqtt",
            )["reason"]
            == "unassigned_sensor"
        )
    assert Reading.objects.count() == 0


def test_replay_conflicts_revocation_qualification(qualified):
    """Reused UUID/sequence, retired hardware and revoked credentials cannot add measurements."""
    payload = event(qualified)
    ingest(qualified["credential"], payload, "https")
    assert (
        ingest(qualified["credential"], {**payload, "value": "1"}, "https")["reason"]
        == "event_conflict"
    )
    assert ingest(qualified["credential"], event(qualified), "https")["reason"] == "sequence_reused"
    sensor = qualified["a"]["sensor"]
    sensor.state = "retired"
    sensor.save()
    assert (
        ingest(qualified["credential"], event(qualified, sequence=2), "https")["reason"]
        == "unqualified_device"
    )
    with patch("sii.telemetry.security.broker", side_effect=TimeoutError):
        with pytest.raises(TimeoutError):
            revoke(qualified["credential"], qualified["world"]["a"]["user"])
    assert (
        ingest(qualified["credential"], event(qualified), "https")["reason"]
        == "credential_inactive"
    )


def test_device_http_surface(qualified):
    """TLS-only device auth is independent of user sessions and never trusts a forwarded header."""
    client = APIClient()
    auth = "Device " + str(qualified["credential"].pk) + "." + qualified["secret"]
    url = "/api/v1/device/ingest/"
    assert (
        client.post(
            url, event(qualified), format="json", secure=True, HTTP_AUTHORIZATION=auth
        ).status_code
        == 404
    )
    with override_settings(ROOT_URLCONF="config.device_urls", SECURE_PROXY_SSL_HEADER=None):
        assert (
            client.post(
                url,
                event(qualified),
                format="json",
                HTTP_AUTHORIZATION=auth,
                HTTP_X_FORWARDED_PROTO="https",
            ).status_code
            == 403
        )
        assert client.post(url, event(qualified), format="json", secure=True).status_code == 403
        result = client.post(
            url, event(qualified), format="json", secure=True, HTTP_AUTHORIZATION=auth
        )
        assert result.status_code == 200
        assert result.json()[0]["status"] == "accepted"
        assert client.get("/api/v1/me/", secure=True).status_code == 404


def test_db_immutable_and_scope_guards(qualified):
    """Bulk SQL cannot rewrite accepted evidence or attach a foreign site's outbox."""
    ingest(qualified["credential"], event(qualified), "https")
    reading = Reading.objects.get()
    with pytest.raises(IntegrityError), transaction.atomic():
        Reading.objects.filter(pk=reading.pk).update(value=10)
    outbox = ProcessingOutbox.objects.get()
    with pytest.raises(IntegrityError), transaction.atomic():
        ProcessingOutbox.objects.filter(pk=outbox.pk).update(site=qualified["b"]["site"])
    process_reading(outbox.pk)
    first = ProcessingOutbox.objects.get().processed_at
    process_reading(outbox.pk)
    assert ProcessingOutbox.objects.get().processed_at == first


def test_manual_import_does_not_touch_gateway(qualified):
    """CSV provenance is permanent and never masquerades as a live gateway heartbeat."""
    result = ingest(qualified["credential"], event(qualified), "csv", source="manual_import")
    assert result["status"] == "accepted"
    assert Reading.objects.get().source == "manual_import"
    qualified["a"]["gateway"].refresh_from_db()
    assert qualified["a"]["gateway"].last_heartbeat_at is None


def test_provisioning_and_scoped_api(qualified):
    """Only exact-scope managers issue secrets; list/metrics never reveal signing material."""
    c = qualified["client"]
    base = endpoint(qualified["a"])
    with patch("sii.telemetry.security.broker") as broker:
        result = post(
            c, base + "device-credentials/", {"gateway": str(qualified["a"]["gateway"].pk)}
        )
        assert result.status_code == 201
        assert len(result.json()["secret"]) > 32
        assert broker.call_count == 3
    assert "secret" not in c.get(base + "device-credentials/").json()["results"][0]
    for route in ["device-credentials/", "readings/", "ingestion-metrics/"]:
        assert c.get(endpoint(qualified["b"]) + route).status_code == 404
    with patch("sii.telemetry.security.broker", side_effect=TimeoutError):
        with pytest.raises(TimeoutError):
            provision(qualified["a"]["gateway"], qualified["world"]["a"]["user"])
    assert DeviceCredential.objects.filter(provisioned=False).exists()
