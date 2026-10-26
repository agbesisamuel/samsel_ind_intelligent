"""Durable broker topology and explicit application acknowledgments for local telemetry.

MQTT PUBACK confirms only RabbitMQ persistence. The consumer persists accepted or
quarantined evidence before ACK. A separate outbox/queue drives idempotent processing.
"""

import hmac
import json
import os
import subprocess
import sys
import time
import uuid
from contextlib import ExitStack
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

from django.db import transaction
from django.utils import timezone
from kombu import Connection, Exchange, Queue

from .models import ProcessingOutbox
from .security import active_credential, broker, secret_for, signature
from .services import ingest, quarantine

TOPIC = Exchange("amq.topic", type="topic", durable=True)
DEAD = Exchange("sii.telemetry.dead", type="direct", durable=True)
WORK = Exchange("sii.telemetry.work", type="direct", durable=True)
DEAD_QUEUE = Queue(
    "sii.telemetry.dead", DEAD, "dead", durable=True, queue_arguments={"x-queue-type": "quorum"}
)
QUEUE_ARGS = {
    "x-queue-type": "quorum",
    "x-delivery-limit": 5,
    "x-dead-letter-exchange": DEAD.name,
    "x-dead-letter-routing-key": "dead",
}
MQTT_QUEUE = Queue("sii.telemetry.in", TOPIC, "ingest.*", durable=True, queue_arguments=QUEUE_ARGS)
WORK_QUEUE = Queue("sii.telemetry.work", WORK, "reading", durable=True, queue_arguments=QUEUE_ARGS)
WORK_SHARDS = [
    Queue(
        f"sii.telemetry.work.{index}",
        WORK,
        f"reading.{index}",
        durable=True,
        queue_arguments=QUEUE_ARGS,
    )
    for index in range(16)
]


def connection():
    """Use a separate telemetry vhost; credentials never appear in logs/CLI arguments."""
    return Connection(
        "amqp://"
        + quote(os.environ["RABBITMQ_DEFAULT_USER"], safe="")
        + ":"
        + quote(os.environ["RABBITMQ_DEFAULT_PASS"], safe="")
        + "@rabbitmq:5672/telemetry",
        heartbeat=30,
        connect_timeout=5,
        transport_options={"confirm_publish": True},
    )


def bootstrap():
    """Idempotently create vhost/topology before allowing any device provisioning."""
    broker("PUT", "vhosts/telemetry", {})
    broker(
        "PUT",
        "permissions/telemetry/" + quote(os.environ["RABBITMQ_DEFAULT_USER"], safe=""),
        {"configure": ".*", "write": ".*", "read": ".*"},
    )
    with connection() as conn:
        for queue in [DEAD_QUEUE, MQTT_QUEUE, WORK_QUEUE, *WORK_SHARDS]:
            queue(conn).declare()


def mqtt_message(body, message):
    """Verify route-bound HMAC, then persist through the same service as HTTPS.

    Unexpected storage failures leave the delivery unacknowledged. Invalid known-device
    data is quarantined and ACKed, avoiding poison loops. Unknown credentials have no
    tenant attribution; reject into the private bounded-delivery dead-letter queue.
    """
    try:
        identifier = uuid.UUID(message.delivery_info["routing_key"].split(".")[1])
        credential = active_credential(identifier)
        if not credential:
            message.reject(requeue=False)
            return
        raw = body.encode() if isinstance(body, str) else body
        if isinstance(raw, bytes):
            if len(raw) > 65536:
                quarantine(credential, raw, "payload_size", "mqtt")
                message.ack()
                return
            try:
                envelope = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                quarantine(credential, raw, "invalid_json", "mqtt")
                message.ack()
                return
        else:
            envelope = raw
        valid = (
            isinstance(envelope, dict)
            and set(envelope) == {"event", "signature"}
            and isinstance(envelope["signature"], str)
        )
        try:
            valid = valid and hmac.compare_digest(
                signature(secret_for(credential), envelope["event"]), envelope["signature"]
            )
        except (ValueError, TypeError):
            valid = False
        if not valid:
            quarantine(credential, raw, "signature_invalid", "mqtt")
        else:
            ingest(credential, envelope["event"], "mqtt")
        message.ack()
    except (ValueError, IndexError, KeyError):
        message.reject(requeue=False)


def process_reading(outbox_id):
    """Evaluate rules/quality inside the acknowledgment transaction; retries remain idempotent."""
    from sii.incidents.services import observe
    from sii.rules.services import evaluate_reading, evaluate_rejection

    with transaction.atomic():
        item = ProcessingOutbox.objects.select_for_update().get(pk=outbox_id)
        if item.processed_at:
            return
        if item.reading_id:
            evaluate_reading(item.reading)
            reading = item.reading
            if reading.source != "manual_import" and not set(reading.quality).intersection(
                {"clock_ahead", "late_backfill"}
            ):
                observe(
                    reading.gateway,
                    None,
                    "invalid_reading",
                    reading.received_at,
                    reading.pk,
                    {"accepted_reading": str(reading.pk)},
                    recovered=True,
                )
        else:
            evaluate_rejection(item.rejection)
        item.processed_at = timezone.now()
        # Only this locked row's delivery timestamp changes; source scope remains DB-guarded.
        ProcessingOutbox.objects.filter(pk=item.pk).update(processed_at=item.processed_at)


def event_envelope(item):
    """Build the versioned domain envelope from persisted scope, never caller-supplied ownership."""
    reading = item.reading
    subject = reading or item.rejection
    return {
        "event_id": str(item.pk),
        "schema_version": 1,
        "event_type": "telemetry.accepted.v1" if reading else "telemetry.rejected.v1",
        "organisation_id": str(item.organisation_id),
        "site_id": str(item.site_id),
        "occurred_at": subject.received_at.isoformat(),
        "correlation_id": str(reading.event_id if reading else subject.pk),
        "actor_or_device_id": str(subject.gateway_id),
        "payload": {"reading_id": str(reading.pk)}
        if reading
        else {"rejection_id": str(subject.pk)},
    }


def work_message(body, message):
    """Only trusted internal publishers reach this queue; validate identifiers before lookup."""
    try:
        identifier = uuid.UUID(body["event_id"])
        item = ProcessingOutbox.objects.select_related("reading").get(pk=identifier)
        # Comparing the complete stored envelope validates schema, references and tenant scope.
        if body != event_envelope(item):
            message.reject(requeue=False)
            return
        process_reading(identifier)
    except (ValueError, TypeError, KeyError, ProcessingOutbox.DoesNotExist):
        message.reject(requeue=False)
        return
    message.ack()


def dispatch(conn):
    """Publish a bounded batch with confirms; retry pending work at most five times.

    Crash after publish but before state update may redeliver. Consumer idempotency
    handles that window. No reading is removed when retries are exhausted.
    """
    with transaction.atomic():
        items = (
            ProcessingOutbox.objects.select_for_update(skip_locked=True)
            .filter(
                processed_at__isnull=True, dead_lettered=False, available_at__lte=timezone.now()
            )
            .order_by("available_at")[:50]
        )
        for item in items:
            if item.attempts >= 5:
                item.dead_lettered = True
                item.save(update_fields=["dead_lettered"])
                continue
            subject = item.reading or item.rejection
            shard = subject.gateway_id.int % len(WORK_SHARDS)
            conn.Producer().publish(
                event_envelope(item),
                exchange=WORK,
                routing_key=f"reading.{shard}",
                serializer="json",
                delivery_mode=2,
                declare=[WORK_SHARDS[shard]],
                retry=False,
            )
            item.attempts += 1
            item.available_at = timezone.now() + timedelta(seconds=min(300, 2**item.attempts * 15))
            ProcessingOutbox.objects.filter(pk=item.pk).update(
                attempts=item.attempts, available_at=item.available_at
            )


def run_worker(shard=0):
    """Keep one serial consumer per gateway shard; only shard zero ingests MQTT.

    Sixteen fixed queues spread gateway skew without competing consumers reordering
    one gateway's rule stream. Shard zero also drains the retained pre-sharding queue.
    Changing this modulus requires a drained queue migration, never a live resize.
    """
    if shard not in range(len(WORK_SHARDS)):
        raise ValueError("Unknown telemetry shard")
    with connection() as conn:
        with ExitStack() as stack:
            if shard == 0:
                stack.enter_context(
                    conn.Consumer(
                        [MQTT_QUEUE],
                        callbacks=[mqtt_message],
                        accept=["json", "text/plain", "application/octet-stream"],
                        prefetch_count=20,
                    )
                )
            with conn.Consumer(
                [WORK_SHARDS[shard], *([WORK_QUEUE] if shard == 0 else [])],
                callbacks=[work_message],
                accept=["json"],
                prefetch_count=20,
            ):
                while True:
                    try:
                        conn.drain_events(timeout=1)
                    except TimeoutError:
                        pass
                    conn.heartbeat_check()
                    Path(f"/tmp/telemetry-shard-{shard}").touch()


def run_publisher():
    """Publish outbox batches independently so confirm/SQL latency never stalls consumers.

    One publisher retains ordered first delivery. Existing bounded retry and durable
    consumer idempotency cover crashes between broker confirmation and DB commit.
    """
    with connection() as conn:
        while True:
            dispatch(conn)
            conn.heartbeat_check()
            Path("/tmp/telemetry-heartbeat").touch()
            time.sleep(0.25)


def run_group(group):
    """Supervise four distinct serial shard processes; restart the group if any child fails.

    Children use independent Django/broker connections and inherit only the service
    environment. The group heartbeat advances only when every child's work loop is
    current. Cleanup terminates only processes created here; durable work is retained.
    """
    if group not in range(4):
        raise ValueError("Unknown shard group")
    shards = list(range(group * 4, group * 4 + 4))
    children = []
    started = time.monotonic()
    try:
        for shard in shards:
            children.append(
                subprocess.Popen(
                    [sys.executable, "manage.py", "telemetry_worker", "run", "--shard", str(shard)]
                )
            )
        while True:
            if any(child.poll() is not None for child in children):
                raise RuntimeError("Telemetry shard exited")
            paths = [Path(f"/tmp/telemetry-shard-{shard}") for shard in shards]
            current = all(
                path.exists() and time.time() - path.stat().st_mtime < 60 for path in paths
            )
            if current:
                Path("/tmp/telemetry-heartbeat").touch()
            elif time.monotonic() - started > 90:
                raise RuntimeError("Telemetry shard heartbeat stalled")
            time.sleep(1)
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
