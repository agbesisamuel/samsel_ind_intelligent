"""Shared durable ingress: validate scope/qualification, deduplicate and commit before receipt."""

import hashlib
import json
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from sii.assets.models import Gateway, Sensor
from sii.assets.services import qualified_query, sensor_qualification

from .contracts import Event
from .models import DeviceCredential, ProcessingOutbox, Reading, Rejection
from .security import canonical


@transaction.atomic
def quarantine(credential, payload, reason, transport):
    """Retain a body digest/size/code; rejected data cannot enter projections or leak secrets."""
    raw = payload if isinstance(payload, bytes) else canonical(payload)
    rejected = Rejection.objects.create(
        organisation=credential.organisation,
        site=credential.site,
        gateway=credential.gateway,
        reason=reason,
        payload_hash=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
        transport=transport,
    )
    ProcessingOutbox.objects.bulk_create(
        [
            ProcessingOutbox(
                organisation=credential.organisation,
                site=credential.site,
                rejection=rejected,
                available_at=timezone.now(),
            )
        ]
    )
    return {"status": "rejected", "reason": reason}


@transaction.atomic
def ingest(credential, payload, transport, source="simulator", preview=False):
    """Commit a reading and outbox together, or a quarantine record, before returning.

    Lock credential then sensor to serialize revoke/dedup. Recheck scope from DB rather
    than trusting a queued object. Unique out-of-order sequence values are allowed;
    reuse with another event is rejected. Only this service chooses source provenance.
    Preview takes the same locks/checks but writes no measurement, rejection or outbox.
    It is advisory; commit always rechecks current device/credential state.
    """

    def reject(reason):
        """Return the same domain reason in preview without persisting rejected input."""
        if preview:
            return {"status": "rejected", "reason": reason}
        return quarantine(credential, payload, reason, transport)

    credential = DeviceCredential.objects.select_for_update().get(pk=credential.pk)
    if (
        not credential.provisioned
        or credential.revoked_at
        or credential.expires_at <= timezone.now()
    ):
        return reject("credential_inactive")
    contract = Event(data=payload)
    if not contract.is_valid():
        return reject("invalid_contract")
    data = contract.validated_data
    # Serialize UUID receipt identity across all sensors and credentials of one gateway.
    Gateway.objects.select_for_update().get(pk=credential.gateway_id)
    sensor = (
        qualified_query(Sensor.objects.select_for_update(of=("self",)))
        .filter(
            pk=data["sensor_id"],
            gateway=credential.gateway,
            site=credential.site,
            organisation=credential.organisation,
        )
        .first()
    )
    if sensor is None:
        return reject("unassigned_sensor")
    qualification = sensor_qualification(sensor)
    if (
        qualification["warnings"]
        or sensor.engineering_min is None
        or sensor.engineering_max is None
        or not sensor.capability_reference
    ):
        return reject("unqualified_device")
    if data["unit"] != sensor.unit:
        return reject("unit_mismatch")
    if not sensor.engineering_min <= data["value"] <= sensor.engineering_max:
        return reject("engineering_range")
    now = timezone.now()
    if not now - timedelta(days=7) <= data["observed_at"] <= now + timedelta(minutes=5):
        return reject("timestamp_window")
    digest = hashlib.sha256(canonical(payload)).hexdigest()
    existing = Reading.objects.filter(gateway=sensor.gateway, event_id=data["event_id"]).first()
    if existing:
        if existing.payload_hash == digest and existing.source == source:
            return {"status": "duplicate", "reading_id": str(existing.pk)}
        return reject("event_conflict")
    sequence = data["sequence"] if source != "manual_import" else None
    if sequence is not None and Reading.objects.filter(sensor=sensor, sequence=sequence).exists():
        return reject("sequence_reused")
    if preview:
        return {"status": "valid"}
    quality = ["synthetic"]
    age = (now - data["observed_at"]).total_seconds()
    if age < -30:
        quality.append("clock_ahead")
    if age > 2 * sensor.expected_interval_sec:
        quality.append("late_backfill")
    if source == "manual_import":
        quality.append("manual_import")
    scope = {"organisation": sensor.organisation, "site": sensor.site}
    reading = Reading(
        **scope,
        sensor=sensor,
        gateway=sensor.gateway,
        event_id=data["event_id"],
        sequence=sequence,
        observed_at=data["observed_at"],
        received_at=now,
        value=data["value"],
        unit=data["unit"],
        payload_hash=digest,
        payload=payload,
        source=source,
        transport=transport,
        quality=quality,
        qualification=json.loads(json.dumps(qualification, default=str)),
    )
    # All fields are service-derived/validated above; DB composite keys and uniqueness
    # protect bulk insertion without repeated full_clean queries for each measurement.
    Reading.objects.bulk_create([reading])
    ProcessingOutbox.objects.bulk_create(
        [ProcessingOutbox(**scope, reading=reading, available_at=now)]
    )
    # Manual imports and buffered samples must not pretend a gateway is currently online.
    if source != "manual_import" and -30 <= age <= 2 * sensor.expected_interval_sec:
        Gateway.objects.filter(pk=sensor.gateway_id).update(last_heartbeat_at=now)
    return {"status": "accepted", "reading_id": str(reading.pk)}
