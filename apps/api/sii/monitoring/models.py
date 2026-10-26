"""QA timing policy, mutable current projections and immutable freshness transition evidence."""

from django.conf import settings
from django.db import models

from sii.assets.models import ScopedAsset, Sensor
from sii.telemetry.models import Reading


class FreshnessPolicy(ScopedAsset):
    """Append-only QA approval of timing and current sensor cadence, independent of alarm rules."""

    sensor_grace_sec = models.PositiveIntegerField()
    gateway_timeout_sec = models.PositiveIntegerField()
    sop_reference = models.CharField(max_length=240)
    intervals = models.JSONField()
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    approved_at = models.DateTimeField(auto_now_add=True)


class SensorState(ScopedAsset):
    """Rebuildable state from immutable observations; null reading is distinct from numeric zero."""

    sensor = models.OneToOneField(Sensor, on_delete=models.PROTECT)
    reading = models.ForeignKey(Reading, null=True, blank=True, on_delete=models.PROTECT)
    status = models.CharField(max_length=30, default="unknown")
    gateway_status = models.CharField(max_length=30, default="unknown")
    evaluated_at = models.DateTimeField()
    last_received_at = models.DateTimeField(null=True, blank=True)
    quality = models.JSONField(default=list, blank=True)


class FreshnessEvent(ScopedAsset):
    """Append-only transition evidence, not a human incident or an automatic safety verdict."""

    sensor = models.ForeignKey(Sensor, on_delete=models.PROTECT)
    occurred_at = models.DateTimeField()
    previous = models.CharField(max_length=30)
    status = models.CharField(max_length=30)
    gateway_status = models.CharField(max_length=30)
