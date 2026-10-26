"""Deterministic current-state calculation and independent sensor/gateway freshness watcher."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from sii.assets.models import Sensor
from sii.assets.services import qualified_query, sensor_qualification
from sii.telemetry.models import Reading, Rejection

from .models import FreshnessEvent, FreshnessPolicy, SensorState


def evaluate(sensor, at):
    """Calculate from a supplied aware clock; manual/future data never makes a live feed fresh.

    Policy captures the exact approved cadence. Changed cadence/new inventory requires
    new QA approval. Both observation and receipt ages must fit the approved window.
    """
    policy = (
        FreshnessPolicy.objects.filter(site=sensor.site, approved_at__lte=at)
        .order_by("-approved_at", "-id")
        .first()
    )
    readings = Reading.objects.filter(sensor=sensor, received_at__lte=at).exclude(
        source="manual_import"
    )
    latest = (
        readings.filter(observed_at__lte=at + timedelta(seconds=30))
        .exclude(quality__contains=["clock_ahead"])
        .order_by("-observed_at", "id")
        .first()
    )
    received = readings.order_by("-received_at").values_list("received_at", flat=True).first()
    qualification = sensor_qualification(sensor, at)
    flags = list(qualification["warnings"])
    if latest:
        flags.extend(latest.quality)
    if readings.filter(
        quality__contains=["clock_ahead"], received_at__gt=at - timedelta(minutes=5)
    ).exists():
        flags.append("recent_clock_ahead")
    status, gateway_status = "unknown", "unknown"
    if not policy or policy.intervals.get(str(sensor.pk)) != sensor.expected_interval_sec:
        status = "policy_missing"
        flags.append("timing_not_approved")
    else:
        heartbeat = sensor.gateway.last_heartbeat_at
        gateway_status = (
            "online"
            if heartbeat and at - timedelta(seconds=policy.gateway_timeout_sec) <= heartbeat <= at
            else "offline"
        )
        if not latest:
            status = "no_data"
        elif qualification["warnings"]:
            status = "unqualified"
        elif gateway_status == "offline":
            status = "gateway_offline"
        else:
            cutoff = at - timedelta(seconds=sensor.expected_interval_sec + policy.sensor_grace_sec)
            status = (
                "fresh"
                if latest.observed_at >= cutoff and latest.received_at >= cutoff
                else "stale"
            )
    if Rejection.objects.filter(
        gateway=sensor.gateway, received_at__gt=at - timedelta(minutes=5), received_at__lte=at
    ).exists():
        flags.append("recent_gateway_rejections")
        if status == "fresh":
            status = "quality_warning"
    if status == "fresh" and "recent_clock_ahead" in flags:
        status = "quality_warning"
    return {
        "reading": latest,
        "status": status,
        "gateway_status": gateway_status,
        "evaluated_at": at,
        "last_received_at": received,
        "quality": sorted(set(flags)),
    }


@transaction.atomic
def refresh_sensor(sensor_id, at=None):
    """Serialize projection updates and emit a transition only when either health state changes."""
    now = at or timezone.now()
    sensor = qualified_query(Sensor.objects.select_for_update(of=("self",)), now).get(pk=sensor_id)
    state = evaluate(sensor, now)
    previous = SensorState.objects.filter(sensor=sensor).first()
    if not previous or (previous.status, previous.gateway_status) != (
        state["status"],
        state["gateway_status"],
    ):
        FreshnessEvent.objects.create(
            organisation=sensor.organisation,
            site=sensor.site,
            sensor=sensor,
            occurred_at=state["evaluated_at"],
            previous=previous.status if previous else "unknown",
            status=state["status"],
            gateway_status=state["gateway_status"],
        )
    projection, _ = SensorState.objects.update_or_create(
        sensor=sensor,
        defaults={
            "organisation": sensor.organisation,
            "site": sensor.site,
            **state,
        },
    )
    return projection


def visible_state(projection, now=None):
    """Fail visibly when the independent watcher stalls; never serve a cached fresh badge."""
    if projection.sensor.state == "retired":
        return "unqualified"
    if (now or timezone.now()) - projection.evaluated_at > timedelta(seconds=60):
        return "watcher_delayed"
    return projection.status
