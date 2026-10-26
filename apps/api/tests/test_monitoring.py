"""Freshness, DST and import boundaries: no missing/manual/future input can imply healthy feed."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from test_assets import endpoint, inventory  # noqa: F401
from test_identity_tenancy import post
from test_telemetry import event, qualified  # noqa: F401

from sii.monitoring.models import FreshnessEvent, FreshnessPolicy
from sii.monitoring.services import refresh_sensor, visible_state
from sii.telemetry.models import Reading, Rejection
from sii.telemetry.services import ingest
from sii.tenants.models import RoleAssignment

pytestmark = pytest.mark.django_db


def approve(fixture, grace=30, gateway=300):
    """Record explicit synthetic QA timing approval; a test policy is never a site go-live."""
    sensor = fixture["a"]["sensor"]
    return FreshnessPolicy.objects.create(
        organisation=sensor.organisation,
        site=sensor.site,
        approved_by=fixture["world"]["a"]["user"],
        sensor_grace_sec=grace,
        gateway_timeout_sec=gateway,
        sop_reference="SYNTHETIC timing SOP",
        intervals={str(sensor.pk): sensor.expected_interval_sec},
    )


def test_zero_missing_policy_and_freshness(qualified):  # noqa: F811
    """Zero is a measurement; no data, missing policy and stale sensors remain distinct."""
    sensor = qualified["a"]["sensor"]
    assert refresh_sensor(sensor.pk).status == "policy_missing"
    approve(qualified)
    assert refresh_sensor(sensor.pk).status == "no_data"
    ingest(qualified["credential"], event(qualified, value="0"), "https")
    projection = refresh_sensor(sensor.pk)
    assert projection.status == "fresh"
    assert projection.reading.value == 0
    assert refresh_sensor(sensor.pk, timezone.now() + timedelta(seconds=91)).status == "stale"
    assert (
        refresh_sensor(sensor.pk, timezone.now() + timedelta(seconds=301)).status
        == "gateway_offline"
    )


def test_stalled_watcher_and_changed_interval(qualified):  # noqa: F811
    """Old projections and cadence changes cannot retain a fresh indication."""
    approve(qualified)
    ingest(qualified["credential"], event(qualified), "https")
    projection = refresh_sensor(qualified["a"]["sensor"].pk)
    assert (
        visible_state(projection, projection.evaluated_at + timedelta(seconds=61))
        == "watcher_delayed"
    )
    sensor = qualified["a"]["sensor"]
    sensor.expected_interval_sec = 90
    sensor.save()
    assert refresh_sensor(sensor.pk).status == "policy_missing"


def test_manual_future_backfill_never_fabricate_freshness(qualified):  # noqa: F811
    """Manual and clock-ahead records cannot supply a live current-state measurement."""
    approve(qualified)
    credential = qualified["credential"]
    ingest(credential, event(qualified), "csv", source="manual_import")
    sensor = qualified["a"]["sensor"]
    assert refresh_sensor(sensor.pk).status == "no_data"
    ingest(
        credential,
        event(
            qualified, sequence=2, observed_at=(timezone.now() + timedelta(minutes=2)).isoformat()
        ),
        "https",
    )
    assert refresh_sensor(sensor.pk).status == "no_data"
    ingest(
        credential,
        event(qualified, sequence=3, observed_at=(timezone.now() - timedelta(hours=1)).isoformat()),
        "mqtt",
    )
    state = refresh_sensor(sensor.pk)
    assert state.status == "gateway_offline"
    assert "late_backfill" in state.quality


def test_late_arrival_does_not_replace_newer_observation(qualified):  # noqa: F811
    """Preserve current observation independently from a newer backfill arrival time."""
    approve(qualified)
    first = ingest(qualified["credential"], event(qualified, sequence=10, value="0"), "https")
    ingest(
        qualified["credential"],
        event(qualified, sequence=2, observed_at=(timezone.now() - timedelta(hours=1)).isoformat()),
        "https",
    )
    state = refresh_sensor(qualified["a"]["sensor"].pk)
    assert str(state.reading_id) == first["reading_id"]
    assert state.last_received_at > state.reading.received_at


def test_policy_authority_scope_and_immutable_evidence(qualified):  # noqa: F811
    """Owner alone cannot approve timing; cross-tenant reads and SQL evidence rewrites fail."""
    client = qualified["client"]
    base = endpoint(qualified["a"])
    payload = {"sensor_grace_sec": 30, "gateway_timeout_sec": 300, "sop_reference": "Synthetic"}
    assert post(client, base + "freshness-policy/", payload).status_code == 201
    RoleAssignment.objects.filter(membership=qualified["world"]["a"]["member"], role="qa").delete()
    assert post(client, base + "freshness-policy/", payload).status_code == 403
    for route in ["monitoring/", "freshness-policy/", "latency/", "series/"]:
        assert client.get(endpoint(qualified["b"]) + route).status_code == 404
    refresh_sensor(qualified["a"]["sensor"].pk)
    count = FreshnessEvent.objects.count()
    refresh_sensor(qualified["a"]["sensor"].pk)
    assert FreshnessEvent.objects.count() == count
    with pytest.raises(IntegrityError), transaction.atomic():
        FreshnessPolicy.objects.update(sensor_grace_sec=0)
    with pytest.raises(IntegrityError), transaction.atomic():
        FreshnessEvent.objects.update(status="fresh")


def test_series_dst_fold_gaps_and_foreign_sensor(qualified):  # noqa: F811
    """The repeated Copenhagen 02:00 hour stays two UTC buckets; empty hours stay null."""
    ingest(qualified["credential"], event(qualified), "https")
    sample = Reading.objects.get()
    for index, hour in enumerate([0, 1]):
        # Create historical boundary fixtures without changing the immutable live sample.
        fixture = Reading(
            **{
                field.attname: getattr(sample, field.attname)
                for field in Reading._meta.fields
                if field.name != "id"
            }
        )
        fixture.event_id, fixture.sequence = uuid.uuid4(), index + 100
        fixture.observed_at = datetime(2026, 10, 25, hour, 30, tzinfo=UTC)
        Reading.objects.bulk_create([fixture])
    base = endpoint(qualified["a"])
    query = {
        "sensor": str(qualified["a"]["sensor"].pk),
        "start": "2026-10-25T00:00:00Z",
        "end": "2026-10-25T03:00:00Z",
    }
    response = qualified["client"].get(base + "series/", query)
    assert response.status_code == 200
    points = response.json()["points"]
    assert [p["count"] for p in points] == [1, 1, 0]
    assert points[0]["average"] == "0.0000"
    assert points[2]["average"] is None
    assert points[0]["start"] != points[1]["start"]
    raw = qualified["client"].get(base + "readings/", query)
    assert raw.status_code == 200
    assert raw.json()["count"] == 2
    assert {row["sensor"] for row in raw.json()["results"]} == {query["sensor"]}
    query["sensor"] = str(qualified["b"]["sensor"].pk)
    assert qualified["client"].get(base + "series/", query).status_code == 404
    assert qualified["client"].get(base + "readings/", query).status_code == 404
    query["start"] = "2026-01-01T00:00:00Z"
    assert qualified["client"].get(base + "series/", query).status_code == 400


def test_csv_mapping_preview_and_commit_revalidation(qualified):  # noqa: F811
    """Validate mapped import scope without preview writes; preserve manual provenance on replay."""
    sensor = qualified["a"]["sensor"]
    payload = {
        "credential": str(qualified["credential"].pk),
        "import_id": str(uuid.uuid4()),
        "mapping": {
            "sensor_id": "probe",
            "observed_at": "time",
            "value": "reading",
            "unit": "units",
        },
        "csv": (
            f"probe,time,reading,units\n{sensor.pk},{timezone.now().isoformat()},0,degC\n"
            f"{qualified['b']['sensor'].pk},{timezone.now().isoformat()},4,degC\n"
        ),
        "preview": True,
    }
    url = endpoint(qualified["a"]) + "csv-import/"
    result = post(qualified["client"], url, payload)
    assert result.status_code == 200
    assert [r["status"] for r in result.json()["rows"]] == ["valid", "rejected"]
    assert Reading.objects.count() == Rejection.objects.count() == 0
    payload["preview"] = False
    result = post(qualified["client"], url, payload)
    assert [r["status"] for r in result.json()["rows"]] == ["accepted", "rejected"]
    assert Reading.objects.get().source == "manual_import"
    assert post(qualified["client"], url, payload).json()["rows"][0]["status"] == "duplicate"
