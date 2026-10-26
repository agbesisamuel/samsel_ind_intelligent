"""Append-only synthetic pilot reviews; real site authorization is never a stored boolean here."""

from django.conf import settings
from django.db import models

from sii.assets.models import ScopedAsset


class ReviewKind(models.TextChoices):
    """Share software-review categories across storage, input validation and schemas."""

    DAILY = "daily_health", "daily_health"
    WEEKLY = "weekly_feedback", "weekly_feedback"


class PilotReview(ScopedAsset):
    """Preserve a scoped daily-health or weekly-feedback observation with server-derived counts."""

    kind = models.CharField(max_length=24, choices=ReviewKind.choices)
    note = models.CharField(max_length=1000)
    snapshot = models.JSONField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)
    synthetic = models.BooleanField(default=True, editable=False)

    class Meta(ScopedAsset.Meta):
        """Raw writes cannot fabricate non-synthetic or unrecognised approval types."""

        constraints = [
            *ScopedAsset.Meta.constraints,
            models.CheckConstraint(condition=models.Q(synthetic=True), name="pilot_synthetic_only"),
            models.CheckConstraint(
                condition=models.Q(kind__in=["daily_health", "weekly_feedback"]),
                name="pilot_review_kind",
            ),
        ]
