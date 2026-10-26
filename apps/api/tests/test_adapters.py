"""Protect source clocks, durable replay/ACK, immutable scoped reviews and real-profile denial."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from test_assets import endpoint, inventory  # noqa: F401
from test_identity_tenancy import post

from sii.adapters.models import PilotReview
from sii.adapters.sdk import Profile, ReplayBuffer, Sample


def test_sdk_reopen_and_durable_receipt(tmp_path):
    """Restart cannot lose values, replace source clocks or treat PUBACK as application storage."""
    gateway, sensor = uuid.uuid4(), uuid.uuid4()
    observed = datetime(2026, 10, 20, tzinfo=UTC)
    sample = Sample(sensor, 0, observed, Decimal("0"))
    path = tmp_path / "private.sqlite3"
    with ReplayBuffer(path, gateway) as buffer:
        identifier = buffer.enqueue(sample)
        assert buffer.enqueue(sample) == identifier
        buffer.discontinuity(observed, observed + timedelta(minutes=5))
        with pytest.raises(ValueError):
            buffer.acknowledge(identifier, {"status": "PUBACK"})
        with pytest.raises(ValueError):
            buffer.enqueue(Sample(sensor, 0, observed, Decimal("1")))
    with pytest.raises(ValueError):
        ReplayBuffer(path, uuid.uuid4())
    with ReplayBuffer(path, gateway) as buffer:
        event = buffer.pending()[0]
        assert event["value"] == "0" and event["observed_at"] == observed.isoformat()
        receipt = {"status": "accepted", "reading_id": str(uuid.uuid4())}
        buffer.acknowledge(identifier, receipt)
        assert buffer.pending() == []
        with pytest.raises(ValueError):
            buffer.acknowledge(identifier, {**receipt, "reading_id": str(uuid.uuid4())})


@pytest.mark.parametrize(
    "value,unit", [("NaN", "degC"), ("151", "degC"), ("0.00001", "degC"), ("4", "degF")]
)
def test_sdk_rejects_unqualified_values(value, unit):
    """No silent unit conversion, rounding or non-finite values enter the supported profile."""
    with pytest.raises(ValueError):
        Sample(uuid.uuid4(), 1, datetime.now(UTC), Decimal(value), unit).event(uuid.uuid4())


def test_sdk_never_claims_real_hardware_or_guesses_time():
    """Configuration cannot declare partner compatibility, writes or a missing source timezone."""
    for options in [{"read_only": False}, {"synthetic": False}, {"code": "claimed-vendor"}]:
        with pytest.raises(ValueError):
            Profile(**options)
    with pytest.raises(ValueError):
        Sample(uuid.uuid4(), 1, datetime(2026, 1, 1), Decimal("4")).event(uuid.uuid4())


@pytest.mark.django_db
def test_scoped_pilot_reviews_cannot_authorise_live(inventory):  # noqa: F811
    """Owner review remains synthetic/blocked; foreign routes and raw SQL amendments are denied."""
    client, base = inventory["client"], endpoint(inventory["a"])
    assert client.get(base + "adapter-readiness/").json()["live_enabled"] is False
    for route in ["adapter-readiness/", "pilot-reviews/"]:
        assert client.get(endpoint(inventory["b"]) + route).status_code == 404
    data = {"kind": "daily_health", "note": "SYNTHETIC daily software review"}
    assert post(client, base + "pilot-reviews/", {**data, "synthetic": False}).status_code == 400
    response = post(client, base + "pilot-reviews/", data)
    assert response.status_code == 201
    assert response.data["snapshot"]["live_enabled"] is False
    review = PilotReview.objects.get()
    with pytest.raises(IntegrityError), transaction.atomic():
        PilotReview.objects.bulk_create(
            [
                PilotReview(
                    organisation=review.organisation,
                    site=review.site,
                    recorded_by=review.recorded_by,
                    kind="daily_health",
                    note="SYNTHETIC forged real claim",
                    snapshot={},
                    synthetic=False,
                )
            ]
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        PilotReview.objects.filter(pk=review.pk).update(note="Rewritten approval")
    with pytest.raises(IntegrityError), transaction.atomic():
        PilotReview.objects.filter(pk=review.pk).update(site=inventory["b"]["site"])
