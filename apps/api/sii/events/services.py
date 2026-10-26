"""Collect only committed immutable sources, publish confirmed envelopes, validate before ACK.

This broker contract complements domain-specific operational queues. Consumers never
derive authority from submitted tenant IDs and cannot rewrite incident/report state.
The durable receipt proves internal delivery, not human acknowledgement or safety.
"""

import time
import uuid
from datetime import timedelta
from pathlib import Path

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from kombu import Exchange, Queue

from sii.incidents.models import IncidentEvent
from sii.monitoring.models import FreshnessEvent
from sii.notifications.models import NotificationAttempt
from sii.reports.models import ReportEvent
from sii.telemetry.transport import DEAD, DEAD_QUEUE, connection

from .models import DomainEvent

EXCHANGE = Exchange("sii.domain", type="topic", durable=True)
QUEUE = Queue(
    "sii.domain.receipts",
    EXCHANGE,
    "#",
    durable=True,
    queue_arguments={
        "x-queue-type": "quorum",
        "x-delivery-limit": 5,
        "x-dead-letter-exchange": DEAD.name,
        "x-dead-letter-routing-key": "dead",
    },
)
SOURCES = {
    "incident": IncidentEvent,
    "freshness": FreshnessEvent,
    "notification": NotificationAttempt,
    "report": ReportEvent,
}


def envelopes(source, name):
    """Build all required envelopes from immutable source fields and exact persisted scope."""
    at = source.occurred_at
    actor, correlation, kinds = None, source.pk, []
    if name == "incident":
        kinds = [source.kind]
        actor, correlation = source.actor_id or source.incident.gateway_id, source.correlation_id
        if (
            source.kind in {"incident.opened.v1", "incident.recurred.v1"}
            and source.incident.rule_version_id
        ):
            kinds.append("rule.breached.v1")
    elif name == "freshness":
        actor = source.sensor.gateway_id
        if source.status == "stale":
            kinds.append("sensor.stale.v1")
        if source.gateway_status == "offline":
            kinds.append("gateway.offline.v1")
    elif name == "notification":
        kinds = ["notification.attempted.v1"]
        actor, correlation = source.notification.contact.user_id, source.notification_id
        if source.outcome != "accepted":
            kinds.append("notification.failed.v1")
    elif name == "report":
        kinds, actor, correlation = [source.event_type], source.job.requested_by_id, source.job_id
    else:
        raise ValueError("Unknown immutable event source")
    return [
        {
            "event_id": str(uuid.uuid5(source.pk, kind)),
            "schema_version": 1,
            "event_type": kind,
            "organisation_id": str(source.organisation_id),
            "site_id": str(source.site_id),
            "occurred_at": at.isoformat(),
            "correlation_id": str(correlation),
            "actor_or_device_id": str(actor) if actor else None,
            "payload": {"source_model": name, "source_id": str(source.pk), "synthetic": True},
        }
        for kind in kinds
    ]


@transaction.atomic
def collect():
    """Catch up bounded committed source batches; one transaction covers multi-envelope sources."""
    for name, model in SOURCES.items():
        query = model.objects.exclude(
            pk__in=DomainEvent.objects.filter(source_model=name).values("source_id")
        )
        if name == "freshness":
            query = query.filter(Q(status="stale") | Q(gateway_status="offline"))
        for source in query.order_by("occurred_at", "id")[:50]:
            for body in envelopes(source, name):
                DomainEvent.objects.get_or_create(
                    pk=body["event_id"],
                    defaults={
                        "organisation_id": source.organisation_id,
                        "site_id": source.site_id,
                        "source_model": name,
                        "source_id": source.pk,
                        "event_type": body["event_type"],
                        "envelope": body,
                        "available_at": timezone.now(),
                    },
                )


def consume(body, message):
    """Compare the complete source-derived envelope before recording an idempotent receipt."""
    try:
        identifier = uuid.UUID(body["event_id"])
        with transaction.atomic():
            event = DomainEvent.objects.select_for_update().get(pk=identifier)
            source = SOURCES[event.source_model].objects.get(
                pk=event.source_id, organisation_id=event.organisation_id, site_id=event.site_id
            )
            if body != event.envelope or body not in envelopes(source, event.source_model):
                raise ValueError("Envelope scope mismatch")
            if event.consumed_at is None:
                DomainEvent.objects.filter(pk=event.pk).update(consumed_at=timezone.now())
    except (ValueError, TypeError, KeyError, DomainEvent.DoesNotExist):
        message.reject(requeue=False)
        return
    message.ack()


@transaction.atomic
def publish(conn):
    """Confirm persistent publication with five bounded attempts and visible dead state."""
    for event in (
        DomainEvent.objects.select_for_update(skip_locked=True)
        .filter(consumed_at__isnull=True, dead_lettered=False, available_at__lte=timezone.now())
        .order_by("available_at")[:50]
    ):
        if event.attempts >= 5:
            DomainEvent.objects.filter(pk=event.pk).update(dead_lettered=True)
            continue
        conn.Producer().publish(
            event.envelope,
            exchange=EXCHANGE,
            routing_key=event.event_type,
            serializer="json",
            delivery_mode=2,
            declare=[QUEUE],
            retry=False,
        )
        DomainEvent.objects.filter(pk=event.pk).update(
            published_at=timezone.now(),
            attempts=event.attempts + 1,
            available_at=timezone.now() + timedelta(seconds=60),
        )


def run():
    """Supervise collection and confirmed transport of committed evidence only."""
    with connection() as conn:
        DEAD_QUEUE(conn).declare()
        QUEUE(conn).declare()
        last = 0.0
        with conn.Consumer([QUEUE], callbacks=[consume], accept=["json"], prefetch_count=20):
            while True:
                if time.monotonic() - last >= 1:
                    collect()
                    publish(conn)
                    last = time.monotonic()
                try:
                    conn.drain_events(timeout=1)
                except TimeoutError:
                    pass
                conn.heartbeat_check()
                Path("/tmp/domain-heartbeat").touch()
