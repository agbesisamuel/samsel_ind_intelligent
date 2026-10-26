"""Protect report scope/cutoffs, qualified gaps, worker retries and single-use export grants."""

import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from test_assets import endpoint, inventory  # noqa: F401
from test_identity_tenancy import post
from test_telemetry import event, qualified  # noqa: F401

from sii.reports import services
from sii.reports.models import ReportJob, ReportSnapshot
from sii.reports.render import render_csv, render_pdf
from sii.reports.snapshot import coverage
from sii.telemetry.services import ingest
from sii.tenants.models import RoleAssignment

pytestmark = pytest.mark.django_db


def test_csv_golden_redacted_formula_text():
    """Golden bytes preserve typed JSON, Unicode and potentially dangerous spreadsheet text."""
    data = {
        key: []
        for key in [
            "readings",
            "coverage",
            "rules",
            "activations",
            "policies",
            "incident_history_through_cutoff",
        ]
    }
    data["label"] = "=HYPERLINK(redacted)"
    expected = (
        '\ufeffrecord_type,canonical_json\r\nmetadata,"{""label"":""=HYPERLINK(redacted)""}"\r\n'
    )
    assert render_csv(data) == expected.encode()


def test_late_backfill_cannot_enter_fixed_snapshot(qualified):  # noqa: F811
    """Post-request arrivals stay outside the snapshot even with earlier observation times."""
    job = request_job(qualified)
    ingest(
        qualified["credential"],
        event(qualified, observed_at=(job.end - timedelta(seconds=30)).isoformat()),
        "https",
    )
    with patch("sii.reports.services.storage.put"):
        services.tick()
    assert ReportSnapshot.objects.get(job=job).data["readings"] == []


def test_operator_cannot_request_or_download_reports(inventory):  # noqa: F811
    """Current export authority is stricter than sensor/incident read authority."""
    job = request_job(inventory)
    member = inventory["world"]["a"]["member"]
    RoleAssignment.objects.filter(membership=member).delete()
    RoleAssignment.objects.create(
        organisation=member.organisation, membership=member, site=job.site, role="operator"
    )
    with pytest.raises(PermissionDenied):
        services.grant(job, job.requested_by)
    assert inventory["client"].get(endpoint(inventory["a"]) + "reports/").status_code == 403


def request_job(fixture, format="csv"):
    """Create a bounded synthetic historical job through the same domain service as HTTP."""
    now = timezone.now()
    return services.request_report(
        fixture["world"]["a"]["user"],
        fixture["a"]["site"],
        {"start": now - timedelta(hours=1), "end": now, "format": format, "locale": "en"},
    )


def test_report_scope_unknown_fields_year_and_offsets(inventory):  # noqa: F811
    """Foreign jobs/zones, mass assignment, year windows and ambiguous timestamps fail closed."""
    client = inventory["client"]
    url = endpoint(inventory["a"]) + "reports/"
    payload = {
        "start": "2026-10-25T02:00:00+02:00",
        "end": "2026-10-25T02:00:00+01:00",
        "format": "csv",
        "locale": "da",
    }
    assert post(client, url, {**payload, "zone": str(inventory["b"]["zone"].pk)}).status_code == 404
    assert post(client, url, {**payload, "status": "ready"}).status_code == 400
    assert post(client, url, {**payload, "end": "2027-10-25T02:00:00Z"}).status_code == 400
    assert post(client, url, {**payload, "start": "2026-10-25T02:00:00"}).status_code == 400
    assert post(client, url, payload).status_code == 202
    assert client.get(endpoint(inventory["b"]) + "reports/").status_code == 404
    job = ReportJob.objects.get()
    assert (
        post(client, endpoint(inventory["a2"]) + f"reports/{job.pk}/access/", {}).status_code == 404
    )


def test_coverage_zero_gap_duplicate_manual_and_unknown():
    """Slot counting preserves zero and gaps; duplicate/manual rows cannot inflate coverage."""
    start = datetime(2026, 10, 25, 0, tzinfo=UTC)
    sensor = {"id": "probe", "expected_interval_sec": 60}
    row = {
        "sensor_id": "probe",
        "observed_at": start.isoformat(),
        "value": "0.0000",
        "source": "simulator",
        "quality": [],
        "qualification": {"warnings": []},
    }
    policy = {"approved_at": start.isoformat(), "intervals": {"probe": 60}}
    result = coverage(
        sensor,
        [row, row, {**row, "source": "manual_import"}],
        [policy],
        start,
        start + timedelta(minutes=3),
    )
    assert result["qualified_slots"] == 1 and result["qualified_percent"] == 33.3333
    assert result["gaps"] == [{"first_slot": 1, "missing_slots": 2}]
    assert (
        coverage(sensor, [row], [], start, start + timedelta(minutes=3))["qualified_percent"]
        is None
    )


def test_async_snapshot_retry_and_single_use(inventory):  # noqa: F811
    """Preserve snapshot across retry and consume each download grant exactly once."""
    job = request_job(inventory)
    user = inventory["world"]["a"]["user"]
    with (
        patch("sii.reports.services.storage.put", side_effect=OSError),
        patch("sii.reports.services.storage.get", side_effect=OSError),
    ):
        services.tick()
    job.refresh_from_db()
    assert job.status == "failed" and job.error_code == "generation_failed"
    snapshot = ReportSnapshot.objects.get(job=job)
    services.retry(job, user)
    with patch("sii.reports.services.storage.put"):
        services.tick()
    job.refresh_from_db()
    assert job.status == "ready" and job.attempts == 2
    assert ReportSnapshot.objects.get(job=job).source_hash == snapshot.source_hash
    body = render_csv(snapshot.data)
    assert hashlib.sha256(body).hexdigest() == job.checksum
    access = services.grant(job, user)
    with patch("sii.reports.services.storage.get", return_value=body):
        assert services.download(job, user, access.pk) == body
        with pytest.raises(NotFound):
            services.download(job, user, access.pk)
    with transaction.atomic(), pytest.raises(IntegrityError):
        ReportSnapshot.objects.filter(pk=snapshot.pk).update(source_hash="0" * 64)
    with transaction.atomic(), pytest.raises(IntegrityError):
        ReportJob.objects.filter(pk=job.pk).update(site=inventory["a2"]["site"])


def test_worker_revocation_and_stalled_lease(inventory):  # noqa: F811
    """Revoked requesters cannot generate exports; expired leases become explicit failure."""
    job = request_job(inventory)
    RoleAssignment.objects.filter(membership=inventory["world"]["a"]["member"]).delete()
    services.tick()
    job.refresh_from_db()
    assert job.status == "failed" and job.error_code == "scope_revoked"
    with pytest.raises(PermissionDenied):
        services.grant(job, job.requested_by)
    ReportJob.objects.filter(pk=job.pk).update(
        status="running", lease_until=timezone.now() - timedelta(seconds=1)
    )
    services.tick()
    job.refresh_from_db()
    assert job.error_code == "worker_lease_expired"


def test_expiry_admission_and_deterministic_pdf(inventory):  # noqa: F811
    """Expiry is immutable; no more than three pending jobs and deterministic safe PDF bytes."""
    job = request_job(inventory, "pdf")
    with patch("sii.reports.services.storage.put"):
        services.tick()
    job.refresh_from_db()
    snapshot = ReportSnapshot.objects.get(job=job)
    body = render_pdf(snapshot.data)
    assert body.startswith(b"%PDF-") and body == render_pdf(snapshot.data)
    with patch("sii.reports.services.timezone.now", return_value=job.expires_at):
        with pytest.raises(ValidationError):
            services.grant(job, job.requested_by)
    for _ in range(3):
        request_job(inventory)
    with pytest.raises(ValidationError):
        request_job(inventory)
