"""Scoped consent, event scheduling and restart-safe local delivery; no customer sends."""

import secrets
import uuid
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from sii.accounts.security import token_digest
from sii.audit.services import record
from sii.incidents.models import IncidentEvent
from sii.rules.models import SuppressionWindow
from sii.tenants.access import sites_for

from . import models, provider


def scope(item):
    """Copy trusted persisted tenant/site keys, never request or queue scope claims."""
    return {"organisation_id": item.organisation_id, "site_id": item.site_id}


def eligible(contact):
    """Recheck consent and current account/site grants before each attempted send."""
    return (
        not contact.disabled
        and contact.verified_at is not None
        and contact.user.is_active
        and contact.user.verified_at is not None
        and sites_for(contact.user, contact.organisation_id).filter(pk=contact.site_id).exists()
    )


def invite(site, user, actor):
    """Email a 30-minute single-use proof through capture; never return it to the caller."""
    if not sites_for(user, site.organisation_id).filter(pk=site.pk).exists():
        raise ValidationError("Account needs an active site grant.")
    token = secrets.token_urlsafe(32)
    contact, _ = models.AlertContact.objects.update_or_create(
        organisation=site.organisation,
        site=site,
        user=user,
        defaults={
            "token_hash": token_digest(token),
            "expires_at": timezone.now() + timedelta(minutes=30),
            "verified_at": None,
            "disabled": False,
        },
    )
    provider.deliver(
        user.email,
        "Confirm notification opt-in",
        "Sign in and confirm this contact in Notifications.\n"
        f"Contact: {contact.pk}\nProof: {token}",
        uuid.uuid4(),
    )
    record(
        "notification.consent_requested",
        actor=actor,
        organisation=site.organisation,
        site=site,
        subject=contact.pk,
    )
    return contact


@transaction.atomic
def confirm(contact, token, user):
    """Only the intended signed-in account can consume its unexpired email opt-in proof."""
    contact = models.AlertContact.objects.select_for_update().get(pk=contact.pk)
    if (
        contact.user_id != user.pk
        or contact.disabled
        or contact.verified_at
        or contact.expires_at <= timezone.now()
        or not secrets.compare_digest(contact.token_hash, token_digest(token))
    ):
        raise PermissionDenied()
    contact.verified_at = timezone.now()
    contact.token_hash = ""
    contact.save(update_fields=["verified_at", "token_hash"])
    record(
        "notification.consent_verified",
        actor=user,
        organisation=contact.organisation,
        site=contact.site,
        subject=contact.pk,
    )
    return contact


def in_shift(route, at):
    """Evaluate local wall-clock shifts across midnight and DST folds."""
    local = at.astimezone(ZoneInfo(route.timezone))
    minute = local.hour * 60 + local.minute
    if route.shift_start < route.shift_end:
        return route.shift_start <= minute < route.shift_end
    return minute >= route.shift_start or minute < route.shift_end


def envelope(event, route, correlation):
    """Versioned immutable dispatch envelope binds scope and the exact persisted source event."""
    return {
        "event_id": str(event.pk if event else correlation),
        "schema_version": 1,
        "event_type": event.kind if event else "notification.test.v1",
        "organisation_id": str(route.organisation_id),
        "site_id": str(route.site_id),
        "occurred_at": event.occurred_at.isoformat() if event else timezone.now().isoformat(),
        "correlation_id": str(event.correlation_id if event else correlation),
        "actor_or_device_id": str(event.actor_id or event.incident.gateway_id) if event else "test",
        "payload": {"incident_id": str(event.incident_id) if event else None, "test": True},
    }


def enqueue(route, contact, level, due, event=None, correlation=None):
    """Persist unique delivery intent; retrying planning cannot duplicate recipient messages."""
    correlation = correlation or uuid.uuid4()
    item, _ = models.Notification.objects.get_or_create(
        dedup_key=f"{event.pk if event else correlation}:{route.pk}:{contact.pk}:{level}",
        defaults={
            **scope(route),
            "route": route,
            "contact": contact,
            "event": event,
            "level": level,
            "due_at": due,
            "envelope": envelope(event, route, correlation),
        },
    )
    return item


@transaction.atomic
def plan(event_id):
    """Lock source identity and atomically plan matching routes or a no-route issue."""
    event = IncidentEvent.objects.select_for_update().get(pk=event_id)
    if models.EventPlan.objects.filter(event=event).exists():
        return
    routes = models.AlertRoute.objects.filter(
        **scope(event), enabled=True, created_at__lte=event.occurred_at
    )
    count = 0
    for route in routes:
        if event.incident.kind not in route.kinds or not in_shift(route, event.occurred_at):
            continue
        count += 1
        enqueue(route, route.contact, "initial", event.occurred_at, event)
        policy = models.EscalationPolicy.objects.filter(route=route).first()
        if policy:
            enqueue(
                route,
                policy.contact,
                "escalation",
                event.occurred_at + timedelta(seconds=policy.delay_sec),
                event,
            )
    models.EventPlan.objects.create(**scope(event), event=event, route_count=count)
    if not count:
        models.DeliveryIssue.objects.get_or_create(
            **scope(event), event=event, defaults={"reason": "no_verified_route"}
        )


def issue(item, reason):
    """Record visible failure and one contingency notification without recursion."""
    models.DeliveryIssue.objects.get_or_create(
        **scope(item), notification=item, defaults={"reason": reason}
    )
    if item.level != "contingency" and item.route.contingency_id:
        enqueue(
            item.route,
            item.route.contingency,
            "contingency",
            timezone.now(),
            item.event,
            correlation=item.pk,
        )


@transaction.atomic
def claim(identifier, at):
    """Validate scope, consent, ack and maintenance; release the lease lock before SMTP."""
    item = (
        models.Notification.objects.select_for_update(of=("self",))
        .select_related("contact__user", "route", "event__incident")
        .get(pk=identifier)
    )
    if item.status not in {"pending", "retry", "deferred_maintenance"} or item.due_at > at:
        return None
    window = None
    if item.event:
        window = (
            SuppressionWindow.objects.filter(**scope(item), start__lte=at, end__gt=at)
            .filter(Q(sensor=item.event.incident.sensor) | Q(sensor__isnull=True))
            .order_by("end")
            .first()
        )
    if item.event and item.envelope != envelope(item.event, item.route, item.pk):
        item.status = "dead"
        issue(item, "invalid_envelope")
    elif not item.route.enabled or not eligible(item.contact):
        item.status = "cancelled"
        issue(item, "recipient_unavailable")
    elif item.level == "escalation" and item.event and item.event.incident.status != "open":
        item.status = "ack_cancelled"
    elif window:
        # Recheck after expiry; maintenance cannot become an implicit permanent mute.
        item.status = "deferred_maintenance"
        item.due_at = window.end
    else:
        item.status = "sending"
        item.attempts += 1
        item.lease_until = at + timedelta(seconds=60)
    item.save(update_fields=["status", "attempts", "lease_until", "due_at"])
    return item if item.status == "sending" else None


@transaction.atomic
def finish(identifier, outcome, reference="", error=""):
    """Append sanitized outcome/retry state; preserve incident human status."""
    item = models.Notification.objects.select_for_update().get(pk=identifier)
    if item.status != "sending":
        return
    models.NotificationAttempt.objects.create(
        organisation=item.organisation,
        site=item.site,
        notification=item,
        number=item.attempts,
        occurred_at=timezone.now(),
        outcome=outcome,
        error_code=error,
    )
    item.status = outcome
    if outcome == "failed":
        item.status = "dead" if item.attempts >= 5 else "retry"
        item.due_at = timezone.now() + timedelta(seconds=min(300, 15 * 2**item.attempts))
    if outcome in {"failed", "uncertain"}:
        issue(item, error)
    if outcome == "accepted":
        models.DeliveryIssue.objects.filter(notification=item, resolved_at__isnull=True).update(
            resolved_at=timezone.now()
        )
    item.provider_reference = reference
    item.lease_until = None
    item.save(update_fields=["status", "due_at", "provider_reference", "lease_until"])
    record(
        "notification.attempted" if outcome == "accepted" else "notification.failed",
        organisation=item.organisation,
        site=item.site,
        subject=item.pk,
        after={"outcome": outcome, "attempt": item.attempts},
    )


def dispatch(identifier, at=None):
    """Perform one leased local send; ambiguous transport failure stops automatic retries."""
    item = claim(identifier, at or timezone.now())
    if item is None:
        return
    try:
        reference = provider.deliver(
            item.contact.user.email,
            f"{item.route.severity}: {item.route.name} ({item.level})",
            f"Site: {item.site_id}\nNotification: {item.pk}\n"
            "Provider acceptance is not human acknowledgement.\n"
            f"Incident: {item.event.incident_id if item.event else 'TEST drill; no incident'}",
            item.pk,
        )
    except provider.DeliveryFailure as exc:
        finish(item.pk, "uncertain" if exc.uncertain else "failed", error=str(exc))
    else:
        finish(item.pk, "accepted", reference=reference)


def tick():
    """Mark lost leases uncertain, then plan and dispatch bounded batches."""
    now = timezone.now()
    for identifier in models.Notification.objects.filter(
        status="sending", lease_until__lte=now
    ).values_list("id", flat=True)[:100]:
        finish(identifier, "uncertain", error="worker_lease_lost")
    for identifier in (
        IncidentEvent.objects.filter(
            kind__in=["incident.opened.v1", "incident.recurred.v1"], eventplan__isnull=True
        )
        .order_by("occurred_at")
        .values_list("id", flat=True)[:100]
    ):
        plan(identifier)
    for identifier in (
        models.Notification.objects.filter(
            status__in=["pending", "retry", "deferred_maintenance"], due_at__lte=now
        )
        .order_by("due_at")
        .values_list("id", flat=True)[:100]
    ):
        dispatch(identifier)
