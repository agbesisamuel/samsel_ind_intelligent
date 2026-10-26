"""Seeded fictional gateway with a persistent SQLite spool and verified TLS transports.

Never reads equipment or sends control commands. Synthetic capabilities, placement
and calibration exist only for the reserved demo namespace and cannot authorize a site.
"""

import json
import random
import sqlite3
import ssl
import threading
import time
import urllib.request
import uuid
from datetime import timedelta
from pathlib import Path

import paho.mqtt.client as mqtt
from django.conf import settings
from django.core.management.base import CommandError
from django.utils import timezone

from sii.accounts.models import CustomUser
from sii.assets.models import CalibrationRecord, Gateway, Sensor, SensorCommissioning, Zone
from sii.audit.services import record
from sii.tenants.management.commands.seed_demo import demo_id
from sii.tenants.models import Organisation, Site

from .models import ProcessingOutbox, Reading
from .security import canonical, provision, revoke, signature, username


def prepare():
    """Create a dedicated simulator probe without changing the original unqualified demo probe."""
    if settings.ENVIRONMENT != "local" or settings.DATABASES["default"]["NAME"] != "sii_local":
        raise CommandError("Simulator requires the synthetic local database")
    org = Organisation.objects.get(pk=demo_id("A"), is_demo=True)
    site = Site.objects.get(pk=demo_id("A/site/1"), organisation=org)
    zone = Zone.objects.get(pk=demo_id("A/1/zone"), organisation=org, site=site)
    actor = CustomUser.objects.get(pk=demo_id("operator@example.invalid"))
    scope = {"organisation": org, "site": site}
    gateway, _ = Gateway.objects.get_or_create(
        pk=demo_id("transport/gateway"),
        defaults={
            **scope,
            "external_id": "synthetic-transport",
            "name": "SYNTHETIC transport simulator",
            "state": "commissioning",
        },
    )
    sensor, _ = Sensor.objects.get_or_create(
        pk=demo_id("transport/sensor"),
        defaults={
            **scope,
            "gateway": gateway,
            "zone": zone,
            "external_id": "synthetic-transport",
            "name": "SYNTHETIC transport probe",
            "state": "commissioning",
            "expected_interval_sec": 60,
            "engineering_min": -100,
            "engineering_max": 150,
            "capability_reference": "SII synthetic profile v1; no physical compatibility claim",
        },
    )
    for item in [gateway, sensor]:
        if (item.organisation_id, item.site_id) != (org.pk, site.pk) or item.state == "retired":
            raise CommandError("Reserved simulator identity/scope mismatch")
    if not sensor.calibrations.filter(due_at__gt=timezone.now()).exists():
        CalibrationRecord.objects.create(
            **scope,
            sensor=sensor,
            recorded_by=actor,
            reference="SYNTHETIC fixture; not physical calibration",
            checked_at=timezone.now() - timedelta(days=1),
            due_at=timezone.now() + timedelta(days=30),
        )
    if not sensor.commissionings.exists():
        SensorCommissioning.objects.create(
            **scope,
            sensor=sensor,
            recorded_by=actor,
            technician_reference="SYNTHETIC fixture author",
            placement_reference="Software only",
            read_only_scope=True,
        )
    record("demo.simulator_prepared", actor=actor, organisation=org, site=site, subject=sensor.pk)
    return sensor, actor


def scenarios(sensor, count, seed, run_id, base_time):
    """Generate normal/warm/cold/jitter/gap/backfill/out-of-order values without safety labels."""
    rng = random.Random(seed)
    sequence_base = int(base_time.timestamp() * 1_000_000)
    events = []
    for index in range(count):
        phase = index % 5
        value = [4, 12, -15, 4 + rng.uniform(-2, 2), 0][phase]
        # Ten-minute synthetic discontinuity is a gap, not fabricated observations.
        seconds = (count - index) * 2 + (600 if index < count // 2 else 0)
        events.append(
            {
                "version": 1,
                "event_id": str(uuid.uuid5(run_id, str(index))),
                "sensor_id": str(sensor.pk),
                "sequence": sequence_base + index,
                "observed_at": (base_time - timedelta(seconds=seconds)).isoformat(),
                "value": f"{value:.4f}",
                "unit": "degC",
            }
        )
    rng.shuffle(events)
    return events


def http(credential, secret, payload=None, receipt=None):
    """Verify the local CA and hostname; never disable certificate verification."""
    path = f"receipts/{receipt}/" if receipt else "ingest/"
    request = urllib.request.Request(
        "https://device-api:8443/api/v1/device/" + path,
        data=canonical(payload) if payload is not None else None,
        headers={
            "Authorization": f"Device {credential.pk}.{secret}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(
        request, timeout=30, context=ssl.create_default_context(cafile="/tls-public/ca.crt")
    ) as response:
        return json.load(response)


def run(count=1000, seed=42):
    """Exercise both transports, malformed input, duplicates and durable offline spool recovery.

    SQLite FULL synchronous commits the unsent batch before any network call. Delivered
    flags are set only after application receipts, not MQTT publish acknowledgments.
    On failure the file remains on a named volume for explicit resume/inspection.
    """
    sensor, actor = prepare()
    run_id = uuid.uuid4()
    events = scenarios(sensor, count, seed, run_id, timezone.now())
    spool_path = Path("/simulator") / (str(run_id) + ".sqlite3")
    with sqlite3.connect(spool_path) as spool:
        spool.execute("PRAGMA synchronous=FULL")
        spool.execute(
            "CREATE TABLE spool (id TEXT PRIMARY KEY, payload TEXT NOT NULL, "
            "delivered INTEGER NOT NULL DEFAULT 0)"
        )
        spool.executemany(
            "INSERT INTO spool(id,payload) VALUES (?,?)",
            [(e["event_id"], canonical(e).decode()) for e in events],
        )
        spool.commit()
    # Reopening proves the producer does not rely on Paho's volatile session memory.
    with sqlite3.connect(spool_path) as spool:
        events = [
            json.loads(row[0]) for row in spool.execute("SELECT payload FROM spool ORDER BY id")
        ]
    credential, secret = provision(sensor.gateway, actor)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="synthetic-" + run_id.hex)
    client.username_pw_set(username(credential), secret)
    client.tls_set(ca_certs="/tls-public/ca.crt")
    try:
        half = count // 2
        for start in range(0, half, 50):
            receipts = http(credential, secret, events[start : min(start + 50, half)])
            if any(item["status"] != "accepted" for item in receipts):
                raise CommandError("HTTPS simulator event rejected; inspect scoped metrics")
        client.connect("rabbitmq", 8883, keepalive=30)
        client.loop_start()
        for event in events[half:]:
            result = client.publish(
                "ingest/" + credential.id.hex,
                canonical({"event": event, "signature": signature(secret, event)}),
                qos=1,
            )
            result.wait_for_publish(timeout=10)
            if not result.is_published():
                raise CommandError("MQTT publish not confirmed; spool retained")
        # Format/range/spoof errors must persist rejection metadata, never measurements.
        malformed = [
            {**events[0], "event_id": str(uuid.uuid4()), "value": "999"} for _ in range(10)
        ]
        malformed += [
            {**events[0], "sensor_id": str(uuid.uuid4())},
            {**events[0], "organisation": str(uuid.uuid4())},
        ]
        if any(r["status"] != "rejected" for r in http(credential, secret, malformed)):
            raise CommandError("Malformed simulator event was accepted")
        for _ in range(2):
            if any(r["status"] != "duplicate" for r in http(credential, secret, events[:50])):
                raise CommandError("Duplicate storm was not idempotent")
        deadline = time.monotonic() + 180
        ids = [e["event_id"] for e in events]
        while time.monotonic() < deadline:
            accepted = Reading.objects.filter(sensor=sensor, event_id__in=ids).count()
            pending = ProcessingOutbox.objects.filter(
                reading__sensor=sensor, reading__event_id__in=ids, processed_at__isnull=True
            ).count()
            if accepted == count and pending == 0:
                break
            time.sleep(1)
        else:
            raise CommandError(
                f"Expected {count} processed events; accepted={accepted}, pending={pending}"
            )
        # Check HTTP application receipt for an MQTT event, not merely broker delivery.
        if http(credential, secret, receipt=events[-1]["event_id"])["status"] != "accepted":
            raise CommandError("Missing MQTT application receipt")
        with sqlite3.connect(spool_path) as spool:
            spool.execute("UPDATE spool SET delivered=1")
            spool.commit()
        # An exact gateway topic ACL must disconnect a publisher targeting another identity.
        denied = threading.Event()

        def on_disconnect(_client, _userdata, _flags, _reason, _properties):
            """Observe broker rejection without printing protocol credentials/payloads."""
            denied.set()

        client.on_disconnect = on_disconnect
        client.publish(
            "ingest/" + uuid.uuid4().hex,
            canonical({"event": events[0], "signature": signature(secret, events[0])}),
            qos=1,
        )
        if not denied.wait(10):
            raise CommandError("Broker did not reject a foreign gateway topic")
        return {
            "accepted": accepted,
            "malformed_rejected": len(malformed),
            "duplicates": 100,
            "pending": pending,
            "foreign_topic_rejected": True,
            "run_id": str(run_id),
            "spool": str(spool_path),
        }
    finally:
        client.disconnect()
        client.loop_stop()
        revoke(credential, actor)
