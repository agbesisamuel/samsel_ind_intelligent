"""Durable local notification queue; provider acceptance never represents human acknowledgement."""

from django.conf import settings
from django.db import models

from sii.assets.models import ScopedAsset
from sii.incidents.models import IncidentEvent
from sii.tenants.models import validate_timezone


class AlertContact(ScopedAsset):
    """Site-granted account opts in with expiring email proof; no arbitrary destination input."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    token_hash = models.CharField(max_length=64, blank=True)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    disabled = models.BooleanField(default=False)

    class Meta(ScopedAsset.Meta):
        """One consent identity per account and site; reenrollment preserves route references."""

        constraints = [
            *ScopedAsset.Meta.constraints,
            models.UniqueConstraint(fields=["site", "user"], name="alert_contact_site_user"),
        ]


class AlertRoute(ScopedAsset):
    """Immutable routing content; only enabled can change with a separate audit event."""

    name = models.CharField(max_length=120)
    contact = models.ForeignKey(AlertContact, on_delete=models.PROTECT, related_name="routes")
    contingency = models.ForeignKey(
        AlertContact,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="contingency_routes",
    )
    kinds = models.JSONField()
    severity = models.CharField(max_length=20)
    timezone = models.CharField(max_length=64, validators=[validate_timezone])
    shift_start = models.PositiveIntegerField()
    shift_end = models.PositiveIntegerField()
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)


class EscalationPolicy(ScopedAsset):
    """Explicit secondary verified contact and non-acknowledgement delay for one route."""

    route = models.OneToOneField(AlertRoute, on_delete=models.PROTECT)
    contact = models.ForeignKey(AlertContact, on_delete=models.PROTECT)
    delay_sec = models.PositiveIntegerField()


class EventPlan(ScopedAsset):
    """Transactional scheduling ledger prevents restart floods and records unrouted events."""

    event = models.OneToOneField(IncidentEvent, on_delete=models.PROTECT)
    planned_at = models.DateTimeField(auto_now_add=True)
    route_count = models.PositiveIntegerField()


class Notification(ScopedAsset):
    """Durable delivery intent with bounded retry/lease state and immutable source envelope."""

    route = models.ForeignKey(AlertRoute, on_delete=models.PROTECT)
    contact = models.ForeignKey(AlertContact, on_delete=models.PROTECT)
    event = models.ForeignKey(IncidentEvent, null=True, blank=True, on_delete=models.PROTECT)
    dedup_key = models.CharField(max_length=180, unique=True)
    level = models.CharField(max_length=20)
    envelope = models.JSONField()
    status = models.CharField(max_length=30, default="pending")
    due_at = models.DateTimeField()
    lease_until = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    provider_reference = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class NotificationAttempt(ScopedAsset):
    """Append-only outcome; a lost worker lease produces uncertain evidence, never blind resend."""

    notification = models.ForeignKey(Notification, on_delete=models.PROTECT, related_name="history")
    number = models.PositiveIntegerField()
    occurred_at = models.DateTimeField()
    outcome = models.CharField(max_length=30)
    error_code = models.CharField(max_length=40, blank=True)

    class Meta(ScopedAsset.Meta):
        """Exactly one recorded outcome per claimed attempt."""

        constraints = [
            *ScopedAsset.Meta.constraints,
            models.UniqueConstraint(
                fields=["notification", "number"], name="notification_attempt_once"
            ),
        ]


class DeliveryIssue(ScopedAsset):
    """Visible delivery-support signal kept separate from industrial incidents and safety claims."""

    notification = models.OneToOneField(
        Notification, null=True, blank=True, on_delete=models.PROTECT
    )
    event = models.OneToOneField(IncidentEvent, null=True, blank=True, on_delete=models.PROTECT)
    reason = models.CharField(max_length=40)
    opened_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
