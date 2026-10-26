"""Incident identity and immutable chronology; automatic recovery never changes human status."""

from django.conf import settings
from django.db import models

from sii.assets.models import Gateway, ScopedAsset, Sensor


class Incident(ScopedAsset):
    """A synthetic unresolved episode, independently scoped to a sensor or entire gateway."""

    sensor = models.ForeignKey(Sensor, null=True, blank=True, on_delete=models.PROTECT)
    gateway = models.ForeignKey(Gateway, on_delete=models.PROTECT)
    rule_version = models.ForeignKey(
        "rules.RuleVersion", null=True, blank=True, on_delete=models.PROTECT
    )
    kind = models.CharField(
        max_length=30,
        choices=[
            (name, name)
            for name in [
                "too_warm",
                "too_cold",
                "rapid_change",
                "invalid_reading",
                "sensor_no_data",
                "gateway_offline",
            ]
        ],
    )
    status = models.CharField(max_length=30, default="open")
    opened_at = models.DateTimeField()
    recovered_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="assigned_incidents",
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=0)
    synthetic = models.BooleanField(default=True, editable=False)

    class Meta(ScopedAsset.Meta):
        """Only one unresolved incident per sensor/gateway classification, including null sensor."""

        constraints = [
            *ScopedAsset.Meta.constraints,
            models.UniqueConstraint(
                fields=["gateway", "sensor", "kind"],
                condition=~models.Q(status="closed"),
                nulls_distinct=False,
                name="incident_unresolved_unique",
            ),
        ]


class IncidentEvent(ScopedAsset):
    """Immutable actor/time/evidence record; recovery and amendments append history."""

    incident = models.ForeignKey(Incident, on_delete=models.PROTECT, related_name="events")
    kind = models.CharField(max_length=60)
    occurred_at = models.DateTimeField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT
    )
    evidence = models.JSONField(default=dict, blank=True)
    correlation_id = models.UUIDField()

    class Meta(ScopedAsset.Meta):
        """Stable correlation makes repeated worker delivery harmless."""

        constraints = [
            *ScopedAsset.Meta.constraints,
            models.UniqueConstraint(
                fields=["incident", "kind", "correlation_id"], name="incident_event_once"
            ),
        ]


class EvidenceAttachment(ScopedAsset):
    """Immutable encrypted plain-text attachment metadata; object keys are server-owned."""

    incident = models.ForeignKey(Incident, on_delete=models.PROTECT)
    object_key = models.CharField(max_length=250, unique=True)
    checksum = models.CharField(max_length=64)
    size = models.PositiveIntegerField()
    label = models.CharField(max_length=120)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    uploaded_at = models.DateTimeField(auto_now_add=True)
