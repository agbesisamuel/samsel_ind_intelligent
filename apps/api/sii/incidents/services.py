"""Idempotent synthetic incident evidence; recovery cannot close the human response lifecycle."""

from django.db import transaction
from django.db.models import Q

from sii.assets.models import Gateway
from sii.rules.models import SuppressionWindow

from .models import Incident, IncidentEvent


@transaction.atomic
def observe(gateway, sensor, kind, at, correlation, evidence, version=None, recovered=False):
    """Serialize episodes per gateway; preserve visible suppression and recurrence evidence."""
    Gateway.objects.select_for_update().get(pk=gateway.pk)
    scope = {"organisation": gateway.organisation, "site": gateway.site}
    incident = (
        Incident.objects.filter(**scope, gateway=gateway, sensor=sensor, kind=kind)
        .exclude(status="closed")
        .first()
    )
    if recovered and not incident:
        return None
    window = (
        SuppressionWindow.objects.filter(**scope, start__lte=at, end__gt=at)
        .filter(Q(sensor=sensor) | Q(sensor__isnull=True))
        .order_by("end")
        .first()
    )
    details = {
        **evidence,
        "synthetic": True,
        "suppression": str(window.pk) if window else None,
        "suppressed_until": window.end.isoformat() if window else None,
    }
    event_kind = "incident.recovered.v1" if recovered else "incident.opened.v1"
    if not incident:
        incident = Incident.objects.create(
            **scope, gateway=gateway, sensor=sensor, kind=kind, rule_version=version, opened_at=at
        )
    elif recovered:
        if incident.recovered_at:
            return incident
        latest_breach = (
            incident.events.filter(kind__in=["incident.opened.v1", "incident.recurred.v1"])
            .order_by("-occurred_at")
            .first()
        )
        if latest_breach and at < latest_breach.occurred_at:
            return incident
        incident.recovered_at = at
        incident.revision += 1
        incident.save(update_fields=["recovered_at", "revision"])
    elif incident.recovered_at:
        event_kind = "incident.recurred.v1"
        incident.recovered_at = None
        # A fresh breach invalidates prior human review; keep its history and assignment.
        incident.acknowledged_at = None
        incident.status = "open"
        incident.revision += 1
        incident.save(update_fields=["recovered_at", "acknowledged_at", "status", "revision"])
    elif incident.events.exists():
        return incident
    IncidentEvent.objects.get_or_create(
        **scope,
        incident=incident,
        kind=event_kind,
        correlation_id=correlation,
        defaults={"occurred_at": at, "evidence": details},
    )
    return incident
