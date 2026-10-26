"""Scoped support capabilities and internal tickets; staff never gain implicit data access."""

import uuid

from django.conf import settings
from django.db import models

from sii.assets.models import ScopedAsset


class SupportSession(ScopedAsset):
    """Owner approval grants diagnostics only; it never adds membership or export authority."""

    supporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="support_sessions"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="support_approvals"
    )
    reason = models.CharField(max_length=500)
    scope = models.CharField(max_length=30, default="diagnostics", editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)


class SupportAccessLog(ScopedAsset):
    """Append-only record of every approved diagnostic read, visible to the customer owner."""

    session = models.ForeignKey(SupportSession, on_delete=models.PROTECT)
    accessed_at = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=40)


class TicketStatus(models.TextChoices):
    """Keep support work separate from the safety-incident lifecycle."""

    OPEN = "open", "open"
    IN_PROGRESS = "in_progress", "in_progress"
    RESOLVED = "resolved", "resolved"


class SupportTicket(ScopedAsset):
    """Preserve original private request content/author beside the response projection."""

    request_id = models.UUIDField(default=uuid.uuid4)
    subject = models.CharField(max_length=160)
    body = models.CharField(max_length=2000)
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=TicketStatus.choices, default="open")
    revision = models.PositiveIntegerField(default=0)
    synthetic = models.BooleanField(default=True, editable=False)

    class Meta(ScopedAsset.Meta):
        """Prevent duplicate requests, invalid support states and forged real provenance."""

        constraints = [
            *ScopedAsset.Meta.constraints,
            models.UniqueConstraint(
                fields=["organisation", "site", "request_id"], name="ticket_request_once"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=TicketStatus.values), name="ticket_status"
            ),
            models.CheckConstraint(condition=models.Q(synthetic=True), name="ticket_local_only"),
        ]


class TicketEvent(ScopedAsset):
    """Append-only customer-workspace conversation, accessible only through current ticket scope."""

    ticket = models.ForeignKey(SupportTicket, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    message = models.CharField(max_length=2000)
    status = models.CharField(max_length=20, choices=TicketStatus.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(ScopedAsset.Meta):
        """Keep raw/bulk event status values inside the supported conversation state machine."""

        constraints = [
            *ScopedAsset.Meta.constraints,
            models.CheckConstraint(
                condition=models.Q(status__in=TicketStatus.values), name="ticket_event_status"
            ),
        ]
