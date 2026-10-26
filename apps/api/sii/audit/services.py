"""Central writer accepts only bounded identifiers/hashes, never credentials or payloads."""

import hashlib
import json

from django.db import transaction
from django.utils import timezone

from .models import AuditEvent, AuditHead


def digest(value):
    """Hash canonical non-secret change data for evidence without persisting full snapshots."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


@transaction.atomic
def record(
    action, *, actor=None, organisation=None, site=None, subject="", before=None, after=None
):
    """Append atomically; validate tenant links and serialize concurrent writers per chain."""
    if site and (not organisation or site.organisation_id != organisation.id):
        raise ValueError("Audit scope mismatch")
    key = str(organisation.id) if organisation else "global"
    AuditHead.objects.get_or_create(key=key)
    head = AuditHead.objects.select_for_update().get(key=key)
    fields = {
        "organisation_id": organisation.id if organisation else None,
        "site_id": site.id if site else None,
        "actor_id": actor.pk if actor and actor.is_authenticated else None,
        "action": action,
        "subject": str(subject),
        "occurred_at": timezone.now(),
        "sequence": head.sequence + 1,
        "before_hash": digest(before) if before is not None else "",
        "after_hash": digest(after) if after is not None else "",
        "prev_hash": head.event_hash,
    }
    event = AuditEvent.objects.create(**fields, event_hash=digest(fields))
    head.sequence = event.sequence
    head.event_hash = event.event_hash
    head.save()
    return event
