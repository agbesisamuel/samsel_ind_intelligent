"""Authorized human incident lifecycle; append-only evidence and optimistic revision checks."""

import uuid

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from sii.accounts.models import CustomUser
from sii.assets.models import Gateway
from sii.assets.services import require_qa
from sii.audit.services import digest, record
from sii.tenants.access import sites_for

from .models import Incident, IncidentEvent

RESPONDERS = ["site_admin", "qa", "operations", "operator"]


def require_responder(user, site, managers=False):
    """Require current operational site authority; auditors/platform staff cannot alter evidence."""
    roles = ["site_admin", "qa", "operations"] if managers else RESPONDERS
    if not sites_for(user, site.organisation_id, roles).filter(pk=site.pk).exists():
        raise PermissionDenied()


def locked(incident):
    """Share gateway-first locking with ingestion so QA closure cannot race a new breach."""
    Gateway.objects.select_for_update().get(pk=incident.gateway_id)
    return Incident.objects.select_for_update().get(pk=incident.pk)


def append(incident, user, kind, evidence, correlation=None):
    """Append actor/time evidence and advance revision; preserve all prior events."""
    incident.revision += 1
    incident.save()
    item = IncidentEvent.objects.create(
        organisation=incident.organisation,
        site=incident.site,
        incident=incident,
        kind=kind,
        occurred_at=timezone.now(),
        actor=user,
        evidence={**evidence, "synthetic": True, "actor_email": user.email},
        correlation_id=correlation or uuid.uuid4(),
    )
    record(
        kind.removesuffix(".v1"),
        actor=user,
        organisation=incident.organisation,
        site=incident.site,
        subject=incident.pk,
        after={"event": str(item.pk), "revision": incident.revision},
    )
    return item


@transaction.atomic
def transition(incident, user, command):
    """Validate role/state/revision and append a replay-safe transition in one transaction."""
    require_responder(user, incident.site)
    item = locked(incident)
    fingerprint = digest({key: str(value) for key, value in command.items() if key != "request_id"})
    previous = IncidentEvent.objects.filter(
        incident=item, correlation_id=command["request_id"]
    ).first()
    if previous:
        if previous.actor_id != user.pk or previous.evidence.get("command_hash") != fingerprint:
            raise ValidationError("Request identifier conflicts with prior evidence.")
        return item
    if item.revision != command["revision"]:
        raise ValidationError("Incident changed; refresh before acting.")
    action, text = command["action"], command["text"]
    if item.status == "closed" and action != "amend":
        raise ValidationError("Closed evidence only accepts explicit amendments.")
    before = item.status
    if action == "acknowledge":
        if item.status != "open":
            raise ValidationError("Only open incidents can be acknowledged.")
        item.status, item.acknowledged_at = "acknowledged", timezone.now()
    elif action == "assign":
        require_responder(user, item.site, managers=True)
        assignee = CustomUser.objects.filter(
            pk=command.get("assignee"), is_active=True, verified_at__isnull=False
        ).first()
        if not assignee:
            raise NotFound()
        require_responder(assignee, item.site)
        item.assigned_to = assignee
    elif action == "investigate":
        if item.status not in {"acknowledged", "investigating"}:
            raise ValidationError("Acknowledge before investigation.")
        item.status = "investigating"
    elif action == "corrective_action":
        if item.status not in {"investigating", "awaiting_qa", "qa_reviewed"}:
            raise ValidationError("Investigate before corrective action.")
        item.status = "awaiting_qa"
    elif action == "qa_review":
        require_qa(user, item.site)
        if item.status != "awaiting_qa":
            raise ValidationError("A corrective action is required before QA review.")
        item.status = "qa_reviewed"
    elif action == "close":
        require_qa(user, item.site)
        if item.status != "qa_reviewed" or item.recovered_at is None:
            raise ValidationError("QA review and observed recovery are required for closure.")
        item.status, item.closed_at = "closed", timezone.now()
    elif action == "amend":
        if item.status == "qa_reviewed":
            item.status = "awaiting_qa"
    else:
        raise ValidationError("Unknown command.")
    kind = {
        "acknowledge": "acknowledged",
        "assign": "assigned",
        "investigate": "investigated",
        "corrective_action": "corrective_action",
        "qa_review": "qa_reviewed",
        "close": "resolved",
        "amend": "amended",
    }[action]
    append(
        item,
        user,
        f"incident.{kind}.v1",
        {
            "text": text,
            "before": before,
            "after": item.status,
            "assigned_to": str(item.assigned_to_id) if item.assigned_to_id else None,
            "command_hash": fingerprint,
        },
        command["request_id"],
    )
    return item
