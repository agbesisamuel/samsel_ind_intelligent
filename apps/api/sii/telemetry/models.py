"""Durable, site-bound ingress evidence and a transactional processing outbox.

Measurements and rejections are append-only in PostgreSQL. Mutable delivery state
is separate so a worker retry cannot alter the evidence it is processing.
"""

from django.db import models

from sii.assets.models import Gateway, ScopedAsset, Sensor


class DeviceCredential(ScopedAsset):
    """One gateway credential; encrypted signing secret is never serialized to readers."""

    gateway = models.ForeignKey(Gateway, on_delete=models.PROTECT)
    encrypted_secret = models.TextField()
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    provisioned = models.BooleanField(default=False)


class Reading(ScopedAsset):
    """Canonical accepted measurement; UUID and sequence are unique per sensor.

    Source is assigned by the server, never by a device. A synthetic source cannot
    become live through replay. Arrival time is the application's first durable receipt.
    """

    gateway = models.ForeignKey(Gateway, on_delete=models.PROTECT)
    sensor = models.ForeignKey(Sensor, on_delete=models.PROTECT)
    event_id = models.UUIDField()
    sequence = models.PositiveBigIntegerField(null=True, blank=True)
    observed_at = models.DateTimeField()
    received_at = models.DateTimeField()
    value = models.DecimalField(max_digits=12, decimal_places=4)
    unit = models.CharField(max_length=12)
    source = models.CharField(max_length=30)
    transport = models.CharField(max_length=10)
    payload_hash = models.CharField(max_length=64)
    payload = models.JSONField()
    quality = models.JSONField(default=list, blank=True)
    qualification = models.JSONField()

    class Meta(ScopedAsset.Meta):
        """Database uniqueness makes duplicate storms safe across concurrent workers."""

        constraints = [
            *ScopedAsset.Meta.constraints,
            models.UniqueConstraint(fields=["sensor", "event_id"], name="reading_event"),
            models.UniqueConstraint(fields=["gateway", "event_id"], name="gateway_event"),
            models.UniqueConstraint(fields=["sensor", "sequence"], name="reading_sequence"),
        ]
        indexes = [models.Index(fields=["organisation", "site", "sensor", "observed_at"])]


class Rejection(ScopedAsset):
    """Quarantine metadata only; arbitrary rejected bodies may contain secrets and are not kept."""

    gateway = models.ForeignKey(Gateway, on_delete=models.PROTECT)
    received_at = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(max_length=50)
    payload_hash = models.CharField(max_length=64)
    byte_count = models.PositiveIntegerField()
    transport = models.CharField(max_length=10)


class ProcessingOutbox(ScopedAsset):
    """Retryable work created atomically with its reading; acknowledged only after processing."""

    reading = models.OneToOneField(Reading, on_delete=models.PROTECT, null=True, blank=True)
    rejection = models.OneToOneField(Rejection, on_delete=models.PROTECT, null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    available_at = models.DateTimeField()
    processed_at = models.DateTimeField(null=True, blank=True)
    dead_lettered = models.BooleanField(default=False)

    class Meta(ScopedAsset.Meta):
        """Exactly one persisted ingress subject owns each versioned processing event."""

        constraints = [
            *ScopedAsset.Meta.constraints,
            models.CheckConstraint(
                condition=(
                    models.Q(reading__isnull=False, rejection__isnull=True)
                    | models.Q(reading__isnull=True, rejection__isnull=False)
                ),
                name="outbox_one_subject",
            ),
        ]
