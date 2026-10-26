"""Immutable scoped envelopes with separate mutable delivery timestamps."""

from django.db import models

from sii.assets.models import ScopedAsset


class DomainEvent(ScopedAsset):
    """Stable source-derived identity; broker duplicates cannot create a second receipt."""

    source_model = models.CharField(max_length=40)
    source_id = models.UUIDField()
    event_type = models.CharField(max_length=60)
    envelope = models.JSONField()
    published_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    available_at = models.DateTimeField()
    dead_lettered = models.BooleanField(default=False)

    class Meta(ScopedAsset.Meta):
        """Stable source/event identity makes collector/transport retries harmless."""

        constraints = [
            *ScopedAsset.Meta.constraints,
            models.UniqueConstraint(
                fields=["source_model", "source_id", "event_type"], name="domain_source_once"
            ),
        ]
