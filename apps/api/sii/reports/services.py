"""Durable report lifecycle with exact-site authorization, bounded leases and no public URLs."""

import hashlib
import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from sii.audit.services import record
from sii.common import storage
from sii.tenants.access import sites_for

from .models import DownloadGrant, ReportEvent, ReportJob, ReportSnapshot
from .render import render_csv, render_pdf
from .snapshot import capture, configuration


def allowed(user, site):
    """Recheck active role assignments for HTTP, workers and downloads; staff grants nothing."""
    return bool(
        user.is_active
        and user.verified_at
        and sites_for(user, site.organisation_id, ["site_admin", "qa", "operations", "auditor"])
        .filter(pk=site.pk)
        .exists()
    )


def require_export(user, site):
    """Operators may inspect data but cannot create/download bulk exports."""
    if not allowed(user, site):
        raise PermissionDenied()


def scope(job):
    """Copy both durable tenant anchors; never derive scope from caller-selected identifiers."""
    return {"organisation_id": job.organisation_id, "site_id": job.site_id}


def event(job, kind):
    """Persist versioned lifecycle evidence and its audit record in the caller's transaction."""
    identifier, now = uuid.uuid4(), timezone.now()
    ReportEvent.objects.create(
        **scope(job),
        job=job,
        pk=identifier,
        event_type=kind,
        occurred_at=now,
        envelope={
            "event_id": str(identifier),
            "schema_version": 1,
            "event_type": kind,
            "organisation_id": str(job.organisation_id),
            "site_id": str(job.site_id),
            "occurred_at": now.isoformat(),
            "correlation_id": str(job.pk),
            "actor_or_device_id": str(job.requested_by_id),
            "payload": {
                "job_id": str(job.pk),
                "status": job.status,
                "checksum": job.checksum,
                "synthetic": True,
            },
        },
    )
    record(
        kind,
        actor=job.requested_by,
        organisation=job.organisation,
        site=job.site,
        subject=job.pk,
        after={"status": job.status},
    )


@transaction.atomic
def request_report(user, site, data, zone=None):
    """Freeze labels and bound active requests; generation remains asynchronous."""
    require_export(user, site)
    # Serialize per-site admission to avoid racing the local three-job resource budget.
    type(site).objects.select_for_update().get(pk=site.pk)
    if ReportJob.objects.filter(site=site, status__in=["queued", "running"]).count() >= 3:
        raise ValidationError("Three reports are already queued/running for this site.")
    now = timezone.now()
    if not timedelta(0) < data["end"] - data["start"] <= timedelta(days=31):
        raise ValidationError("Use an explicit window of at most 31 days; no data is truncated.")
    if zone and (zone.site_id != site.pk or zone.organisation_id != site.organisation_id):
        raise NotFound()
    job = ReportJob.objects.create(
        organisation=site.organisation,
        site=site,
        zone=zone,
        requested_by=user,
        requested_at=now,
        expires_at=now + timedelta(hours=24),
        configuration=configuration(site, zone),
        **data,
    )
    event(job, "report.requested.v1")
    return job


def tick():
    """Recover expired leases visibly and process one bounded job; no silent infinite retries."""
    now = timezone.now()
    with transaction.atomic():
        for job in ReportJob.objects.select_for_update(skip_locked=True).filter(
            status="running", lease_until__lt=now
        )[:10]:
            job.status, job.error_code = "failed", "worker_lease_expired"
            job.save()
            event(job, "report.failed.v1")
        job = (
            ReportJob.objects.select_for_update(skip_locked=True)
            .filter(status="queued")
            .order_by("requested_at")
            .first()
        )
        if not job:
            return
        job.status, job.attempts = "running", job.attempts + 1
        job.lease_until = now + timedelta(minutes=5)
        job.save()
    try:
        require_export(job.requested_by, job.site)
        if job.expires_at <= timezone.now():
            raise ValidationError("Expired")
        snapshot = ReportSnapshot.objects.filter(job=job).first()
        if snapshot is None:
            data, digest = capture(job)
            snapshot = ReportSnapshot.objects.create(
                **scope(job), job=job, data=data, source_hash=digest
            )
        body = (render_pdf if job.format == "pdf" else render_csv)(snapshot.data)
        checksum = hashlib.sha256(body).hexdigest()
        try:
            storage.put(job.organisation_id, job.site_id, job.pk, body)
        except Exception:
            # A crash may leave the immutable object without ready metadata. Recover
            # only if decryption, tenant binding and the deterministic checksum match.
            if storage.get(job.organisation_id, job.site_id, job.pk, checksum) != body:
                raise ValueError("Artifact mismatch") from None
        with transaction.atomic():
            current = ReportJob.objects.select_for_update().get(pk=job.pk)
            if current.status != "running" or current.attempts != job.attempts:
                return
            current.status, current.checksum, current.size = "ready", checksum, len(body)
            current.completed_at, current.lease_until = timezone.now(), None
            current.save()
            event(current, "report.created.v1")
    except Exception as exc:
        # Safe codes only: storage/provider exception strings can contain sensitive URLs.
        code = (
            "scope_revoked"
            if isinstance(exc, PermissionDenied)
            else (
                "reduce_window_or_scope"
                if isinstance(exc, ValidationError)
                else "generation_failed"
            )
        )
        with transaction.atomic():
            current = ReportJob.objects.select_for_update().get(pk=job.pk)
            if current.status == "running" and current.attempts == job.attempts:
                current.status, current.error_code, current.lease_until = "failed", code, None
                current.save()
                event(current, "report.failed.v1")


@transaction.atomic
def retry(job, user):
    """Explicit bounded retry preserves the same immutable cutoff/snapshot and artifact identity."""
    require_export(user, job.site)
    job = ReportJob.objects.select_for_update().get(pk=job.pk)
    if job.status != "failed" or job.attempts >= 3 or job.expires_at <= timezone.now():
        raise ValidationError(
            "Retry unavailable; create a smaller report or investigate the fault."
        )
    job.status, job.error_code = "queued", ""
    job.save()
    event(job, "report.retried.v1")
    return job


def grant(job, user):
    """Issue a five-minute, single-use handle; authentication and current scope remain required."""
    require_export(user, job.site)
    if job.status != "ready" or job.expires_at <= timezone.now():
        raise ValidationError("Artifact unavailable or expired.")
    return DownloadGrant.objects.create(
        **scope(job),
        job=job,
        user=user,
        expires_at=min(job.expires_at, timezone.now() + timedelta(minutes=5)),
    )


@transaction.atomic
def download(job, user, identifier):
    """Consume only after exact-user/site authorization and authenticated ciphertext retrieval."""
    require_export(user, job.site)
    access = (
        DownloadGrant.objects.select_for_update()
        .filter(
            pk=identifier,
            job=job,
            user=user,
            used_at__isnull=True,
            expires_at__gt=timezone.now(),
            job__expires_at__gt=timezone.now(),
            job__status="ready",
        )
        .first()
    )
    if not access:
        raise NotFound()
    body = storage.get(job.organisation_id, job.site_id, job.pk, job.checksum)
    access.used_at = timezone.now()
    access.save()
    record(
        "report.downloaded",
        actor=user,
        organisation=job.organisation,
        site=job.site,
        subject=job.pk,
    )
    return body
