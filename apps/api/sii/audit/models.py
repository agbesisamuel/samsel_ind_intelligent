"""Hash-linked audit events with per-chain locking and database mutation denial."""

import uuid

from django.conf import settings
from django.db import models


class AuditHead(models.Model):
    """Serialize append operations per tenant/global chain without cross-tenant readers."""

    key = models.CharField(max_length=64, primary_key=True)
    sequence = models.PositiveBigIntegerField(default=0)
    event_hash = models.CharField(max_length=64, default="")


class AuditEvent(models.Model):
    """Immutable application evidence; DB administrators still need external oversight."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey("tenants.Organisation", null=True, on_delete=models.PROTECT)
    site = models.ForeignKey("tenants.Site", null=True, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    action = models.CharField(max_length=64)
    subject = models.CharField(max_length=64)
    occurred_at = models.DateTimeField()
    sequence = models.PositiveBigIntegerField()
    before_hash = models.CharField(max_length=64, blank=True)
    after_hash = models.CharField(max_length=64, blank=True)
    prev_hash = models.CharField(max_length=64, blank=True)
    event_hash = models.CharField(max_length=64)

    class Meta:
        """Provide bounded tenant timelines and unique event positions within every chain."""

        ordering = ["-occurred_at", "-sequence"]
        indexes = [models.Index(fields=["organisation", "-occurred_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "sequence"],
                nulls_distinct=False,
                name="audit_chain_sequence",
            )
        ]
