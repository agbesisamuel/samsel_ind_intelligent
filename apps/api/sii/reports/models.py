"""Bounded report intent, immutable snapshot and short-lived identity-bound download grants."""

from django.conf import settings
from django.db import models

from sii.assets.models import ScopedAsset, Zone


class ReportJob(ScopedAsset):
    """Immutable requested scope/window/configuration plus restartable bounded worker status."""

    zone = models.ForeignKey(Zone, null=True, blank=True, on_delete=models.PROTECT)
    start = models.DateTimeField()
    end = models.DateTimeField()
    format = models.CharField(max_length=8, choices=[("pdf", "PDF"), ("csv", "CSV")])
    locale = models.CharField(max_length=2, choices=[("en", "English"), ("da", "Dansk")])
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    requested_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    configuration = models.JSONField()
    status = models.CharField(max_length=20, default="queued")
    attempts = models.PositiveIntegerField(default=0)
    lease_until = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=60, blank=True)
    checksum = models.CharField(max_length=64, blank=True)
    size = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)


class ReportSnapshot(ScopedAsset):
    """Immutable bounded source snapshot; retries never silently change report content."""

    job = models.OneToOneField(ReportJob, on_delete=models.PROTECT)
    data = models.JSONField()
    source_hash = models.CharField(max_length=64)
    captured_at = models.DateTimeField(auto_now_add=True)


class DownloadGrant(ScopedAsset):
    """Single-use five-minute grant bound to a current authorized user, job and artifact expiry."""

    job = models.ForeignKey(ReportJob, on_delete=models.PROTECT)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)


class ReportEvent(ScopedAsset):
    """Immutable versioned lifecycle evidence with source checksum and correlation metadata."""

    job = models.ForeignKey(ReportJob, on_delete=models.PROTECT)
    event_type = models.CharField(max_length=60)
    occurred_at = models.DateTimeField()
    envelope = models.JSONField()
