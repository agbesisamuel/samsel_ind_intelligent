"""Bounded historical evidence; qualification and missing slots never imply food safety."""

import hashlib
import json
import math
from datetime import datetime

from rest_framework.exceptions import ValidationError

from sii.assets.models import CalibrationRecord, Sensor
from sii.incidents.models import IncidentEvent
from sii.monitoring.models import FreshnessPolicy
from sii.rules.models import RuleActivation, RuleVersion
from sii.telemetry.models import Reading

LIMIT = 10000


def canonical(value):
    """Stable UTF-8 representation for immutable snapshots and retry checksums."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def bounded(query):
    """Reject excessive input explicitly; never silently truncate a compliance export."""
    rows = list(query[: LIMIT + 1])
    if len(rows) > LIMIT:
        raise ValidationError("Reduce the report window or zone; maximum 10000 source records.")
    return rows


def configuration(site, zone):
    """Freeze mutable labels/cadence and existing calibration records at request time."""
    sensors = Sensor.objects.filter(site=site).order_by("id")
    if zone:
        sensors = sensors.filter(zone=zone)
    rows = bounded(sensors.values("id", "name", "zone_id", "expected_interval_sec", "unit"))
    if len(rows) > 800:
        raise ValidationError("Reduce scope to at most 800 sensors.")
    history = IncidentEvent.objects.filter(site=site)
    if zone:
        history = history.filter(incident__sensor_id__in=[row["id"] for row in rows])
    return json.loads(
        canonical(
            {
                "site_name": site.name,
                "organisation_name": site.organisation.name,
                "zone_name": zone.name if zone else "All zones",
                "timezone": site.timezone,
                "sensors": rows,
                "incident_event_ids": bounded(history.order_by("id").values_list("id", flat=True)),
                "calibrations": bounded(
                    CalibrationRecord.objects.filter(sensor_id__in=[row["id"] for row in rows])
                    .order_by("checked_at", "id")
                    .values("id", "sensor_id", "reference", "checked_at", "due_at", "synthetic")
                ),
            }
        )
    )


def coverage(sensor, readings, policies, start, end):
    """Count unique qualified cadence slots, not rows; gap runs require no huge slot array.

    A single matching QA cadence must cover the whole interval. Otherwise the estimate
    remains visible but qualified percentage is unknown. Manual/skew/unqualified rows
    remain in raw evidence and never fill a qualified slot.
    """
    interval = sensor["expected_interval_sec"]
    expected = math.ceil((end - start).total_seconds() / interval)
    applicable = [p for p in policies if datetime.fromisoformat(p["approved_at"]) <= start]
    initial = applicable[-1] if applicable else None
    later = [p for p in policies if start < datetime.fromisoformat(p["approved_at"]) < end]
    approved = bool(initial) and all(
        p["intervals"].get(sensor["id"]) == interval for p in [initial, *later]
    )
    slots = sorted(
        {
            int((datetime.fromisoformat(row["observed_at"]) - start).total_seconds() // interval)
            for row in readings
            if row["sensor_id"] == sensor["id"]
            and row["source"] != "manual_import"
            and "clock_ahead" not in row["quality"]
            and not row["qualification"].get("warnings", ["qualification_missing"])
        }
    )
    gaps, previous = [], -1
    for slot in [*slots, expected]:
        if slot > previous + 1:
            gaps.append({"first_slot": previous + 1, "missing_slots": slot - previous - 1})
        previous = slot
    return {
        "sensor": sensor["id"],
        "expected_slots_estimate": expected,
        "qualified_slots": len(slots),
        "qualified_percent": round(100 * len(slots) / expected, 4) if approved else None,
        "cadence_approved_through_window": approved,
        "gaps": gaps,
    }


def capture(job):
    """Freeze bounded append-only evidence at the durable request receipt cutoff.

    Historical incident chronology is exported rather than today's mutable status.
    Backdated imports arriving after the cutoff cannot alter this report on retry.
    """
    sensor_ids = [row["id"] for row in job.configuration["sensors"]]
    readings = bounded(
        Reading.objects.filter(
            site=job.site,
            sensor_id__in=sensor_ids,
            observed_at__gte=job.start,
            observed_at__lt=job.end,
            received_at__lte=job.requested_at,
        )
        .order_by("observed_at", "id")
        .values(
            "id",
            "sensor_id",
            "event_id",
            "observed_at",
            "received_at",
            "value",
            "unit",
            "source",
            "transport",
            "quality",
            "qualification",
            "payload_hash",
        )
    )
    # Events are server-created, append-only. Include earlier context for all selected
    # episodes; label chronology explicitly instead of presenting a current status as historical.
    events = IncidentEvent.objects.filter(
        site=job.site,
        pk__in=job.configuration["incident_event_ids"],
        occurred_at__lte=job.requested_at,
        incident__opened_at__lt=job.end,
    )
    if job.zone_id:
        events = events.filter(incident__sensor_id__in=sensor_ids)
    rules = RuleVersion.objects.filter(site=job.site, created_at__lte=job.requested_at)
    if job.zone_id:
        rules = rules.filter(ruleset__zone_id=job.zone_id)
    data = json.loads(
        canonical(
            {
                "schema_version": 1,
                "synthetic": True,
                "organisation": job.organisation_id,
                "site": job.site_id,
                "zone": job.zone_id,
                "start_inclusive": job.start,
                "end_exclusive": job.end,
                "receipt_cutoff": job.requested_at,
                "configuration": job.configuration,
                "locale": job.locale,
                "provenance": "Raw readings; derived coverage; no interpolation or safety verdict.",
                "readings": readings,
                "policies": bounded(
                    FreshnessPolicy.objects.filter(site=job.site, approved_at__lte=job.requested_at)
                    .order_by("approved_at", "id")
                    .values("id", "approved_at", "intervals", "sensor_grace_sec", "sop_reference")
                ),
                "rules": bounded(rules.order_by("created_at", "id").values()),
                "activations": bounded(
                    RuleActivation.objects.filter(
                        approval__version__in=rules,
                        effective_at__lt=job.end,
                        effective_at__lte=job.requested_at,
                    )
                    .order_by("effective_at", "id")
                    .values()
                ),
                "incident_history_through_cutoff": bounded(
                    events.order_by("occurred_at", "id").values(
                        "id", "incident_id", "kind", "occurred_at", "evidence", "correlation_id"
                    )
                ),
            }
        )
    )
    data["coverage"] = [
        coverage(sensor, data["readings"], data["policies"], job.start, job.end)
        for sensor in job.configuration["sensors"]
    ]
    digest = hashlib.sha256(canonical(data)).hexdigest()
    data["source_hash"] = digest
    return data, digest
