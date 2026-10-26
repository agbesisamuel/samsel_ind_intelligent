"""Scoped rule lifecycle and worker evaluation; stored approvals are required at every use."""

import uuid
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from sii.assets.models import Gateway, Sensor
from sii.assets.services import qualified_query, require_qa, scoped_site, sensor_qualification
from sii.audit.services import digest, record
from sii.incidents.services import observe
from sii.monitoring.models import FreshnessPolicy
from sii.telemetry.models import Reading

from .engine import step
from .models import RuleActivation, RuleApproval, RuleBacktest, RuleCursor, RuleEvaluation, RuleSet


def config(version):
    """Return canonical engine inputs, including DecimalField's four-place DB precision.

    Newly saved models can still hold integer/string inputs in memory. Their snapshot
    must match a subsequent database read or an unchanged approval becomes stale.
    """
    return {
        key: format(Decimal(str(getattr(version, key))), ".4f")
        if key in ["lower_bound", "upper_bound", "hysteresis"]
        else getattr(version, key)
        for key in [
            "lower_bound",
            "upper_bound",
            "hysteresis",
            "sustained_sec",
            "recovery_sec",
            "sop_reference",
        ]
    }


def approval_snapshot(version):
    """Bind a version to qualified zone sensors and current QA cadence; reject missing evidence."""
    policy = (
        FreshnessPolicy.objects.filter(site=version.site).order_by("-approved_at", "-id").first()
    )
    sensors = qualified_query(
        Sensor.objects.filter(
            organisation=version.organisation, site=version.site, zone=version.ruleset.zone
        )
        .exclude(state="retired")
        .order_by("id")
    )
    sensors = list(sensors)
    if not policy or not sensors:
        raise ValidationError("Qualified sensors and QA timing approval required.")
    intervals = {}
    for sensor in sensors:
        if (
            sensor_qualification(sensor)["warnings"]
            or sensor.engineering_min is None
            or sensor.engineering_max is None
            or not sensor.capability_reference
            or policy.intervals.get(str(sensor.pk)) != sensor.expected_interval_sec
        ):
            raise ValidationError(
                "Every zone sensor needs current qualification and timing approval."
            )
        if (
            not sensor.engineering_min
            <= version.lower_bound
            < version.upper_bound
            <= sensor.engineering_max
        ):
            raise ValidationError("Rule bounds exceed registered engineering capability.")
        intervals[str(sensor.pk)] = sensor.expected_interval_sec
    return {
        "version": str(version.pk),
        "config": config(version),
        "intervals": intervals,
        "timing_policy": str(policy.pk),
        "grace": policy.sensor_grace_sec,
    }


def backtest(version, user, start, end):
    """Simulate bounded history; exclude manual, unqualified and clock-skewed inputs."""
    snapshot = approval_snapshot(version)
    rows = Reading.objects.filter(
        organisation=version.organisation,
        site=version.site,
        sensor__zone=version.ruleset.zone,
        observed_at__gte=start,
        observed_at__lt=end,
    ).order_by("observed_at", "id")
    if rows.count() > 10000:
        raise ValidationError("Reduce backtest window to at most 10,000 readings.")
    states, actions, hashes = {}, [], []
    excluded = 0
    for reading in rows:
        hashes.append(reading.payload_hash)
        if (
            reading.source == "manual_import"
            or "clock_ahead" in reading.quality
            or reading.qualification.get("warnings")
        ):
            excluded += 1
            continue
        key = str(reading.sensor_id)
        if key not in snapshot["intervals"]:
            excluded += 1
            continue
        state, changes, _ = step(
            config(version),
            states.get(key, {}),
            reading.observed_at,
            reading.value,
            snapshot["intervals"][key],
            snapshot["grace"],
        )
        states[key] = state
        actions.extend(
            [{**change, "sensor": key, "at": reading.observed_at.isoformat()} for change in changes]
        )
    result = {
        "inputs": len(hashes),
        "excluded": excluded,
        "actions": actions,
        "snapshot": snapshot,
        "synthetic": True,
    }
    return RuleBacktest.objects.create(
        organisation=version.organisation,
        site=version.site,
        version=version,
        start=start,
        end=end,
        result=result,
        input_hash=digest(hashes),
        created_by=user,
    )


def approve(version, backtest_id, user):
    """Bind explicit QA review to a matching, nonempty tested version and current qualification."""
    require_qa(user, version.site)
    test = RuleBacktest.objects.filter(
        pk=backtest_id, version=version, organisation=version.organisation, site=version.site
    ).first()
    if not test:
        raise NotFound()
    snapshot = approval_snapshot(version)
    if test.result["inputs"] - test.result["excluded"] < 2 or test.result["snapshot"] != snapshot:
        raise ValidationError("Run a current backtest with at least two qualified readings first.")
    item = RuleApproval.objects.create(
        organisation=version.organisation,
        site=version.site,
        version=version,
        backtest=test,
        approved_by=user,
        snapshot=snapshot,
        snapshot_hash=digest(snapshot),
    )
    record(
        "rule.approved",
        actor=user,
        organisation=version.organisation,
        site=version.site,
        subject=item.pk,
    )
    return item


@transaction.atomic
def activate(approval, user):
    """Activate under family lock; immutable boundaries define disjoint effective intervals."""
    version = approval.version
    scoped_site(user, version.organisation_id, version.site_id, write=True)
    RuleSet.objects.select_for_update().get(pk=version.ruleset_id)
    if approval.snapshot != approval_snapshot(version):
        raise ValidationError("Approval no longer matches current qualification/timing.")
    previous = (
        RuleActivation.objects.filter(ruleset=version.ruleset).order_by("-effective_at").first()
    )
    if previous and previous.approval.version.version >= version.version:
        raise ValidationError(
            "Activate a newer approved version; superseded evidence cannot be rewritten."
        )
    item = RuleActivation.objects.create(
        organisation=version.organisation,
        site=version.site,
        ruleset=version.ruleset,
        approval=approval,
        effective_at=timezone.now(),
    )
    record(
        "rule.activated",
        actor=user,
        organisation=version.organisation,
        site=version.site,
        subject=item.pk,
    )
    return item


@transaction.atomic
def evaluate_reading(reading):
    """Evaluate approved input once; backfill cannot create a retroactive live breach."""
    active = (
        RuleActivation.objects.filter(
            organisation=reading.organisation,
            site=reading.site,
            ruleset__zone=reading.sensor.zone,
            effective_at__lte=reading.observed_at,
        )
        .select_related("approval__version")
        .order_by("-effective_at")
        .first()
    )
    if not active:
        return
    version, approval = active.approval.version, active.approval
    # Gateway is the shared lock order across ingestion and incident writes.
    Gateway.objects.select_for_update().get(pk=reading.gateway_id)
    if RuleEvaluation.objects.filter(version=version, reading=reading).exists():
        return
    snapshot = approval.snapshot
    reason, actions = "unqualified", []
    # A delayed pre-boundary observation remains evidence under its original version,
    # but must not restart an old cursor after a newer version became effective.
    superseded = RuleActivation.objects.filter(
        ruleset=version.ruleset,
        effective_at__gt=active.effective_at,
        effective_at__lte=reading.received_at,
    ).exists()
    try:
        current = approval_snapshot(version)
    except ValidationError:
        current = None
    if superseded:
        reason = "superseded_late_evidence_only"
    elif current != snapshot:
        reason = "approval_stale"
    elif (
        reading.source == "manual_import"
        or "clock_ahead" in reading.quality
        or reading.qualification.get("warnings")
    ):
        reason = "quality_excluded"
    elif "late_backfill" in reading.quality:
        reason = "backfill_evidence_only"
    else:
        cursor, _ = RuleCursor.objects.get_or_create(
            organisation=reading.organisation,
            site=reading.site,
            version=version,
            sensor=reading.sensor,
        )
        state, actions, reason = step(
            config(version),
            cursor.state,
            reading.observed_at,
            reading.value,
            snapshot["intervals"][str(reading.sensor_id)],
            snapshot["grace"],
        )
        cursor.state = state
        # State is produced by the deterministic engine inside the gateway lock;
        # update only that projection, retaining immutable DB scope anchors.
        RuleCursor.objects.filter(pk=cursor.pk).update(state=state)
        for action in actions:
            observe(
                reading.gateway,
                reading.sensor,
                action["kind"],
                reading.observed_at,
                reading.pk,
                {"reading": str(reading.pk), "rule_version": str(version.pk), **action},
                version=version,
                recovered=action["transition"] == "recovered",
            )
    # Scope and source are derived from the locked reading and selected activation;
    # composite database foreign keys protect this immutable hot-path insertion.
    RuleEvaluation.objects.bulk_create(
        [
            RuleEvaluation(
                organisation=reading.organisation,
                site=reading.site,
                version=version,
                reading=reading,
                result={"reason": reason, "actions": actions, "synthetic": True},
            )
        ]
    )


def evaluate_health(projection):
    """Record independent no-data/offline incidents after the approved initial grace."""
    sensor, at = projection.sensor, projection.evaluated_at
    policy = (
        FreshnessPolicy.objects.filter(site=sensor.site).order_by("-approved_at", "-id").first()
    )
    if not policy or policy.intervals.get(str(sensor.pk)) != sensor.expected_interval_sec:
        return
    missing = not projection.reading or projection.reading.observed_at < at - timedelta(
        seconds=sensor.expected_interval_sec + policy.sensor_grace_sec
    )
    if at >= policy.approved_at + timedelta(
        seconds=sensor.expected_interval_sec + policy.sensor_grace_sec
    ):
        observe(
            sensor.gateway,
            sensor,
            "sensor_no_data",
            at,
            uuid.uuid5(projection.pk, at.isoformat() + "sensor"),
            {"freshness": projection.status},
            recovered=not missing,
        )
    if at >= policy.approved_at + timedelta(seconds=policy.gateway_timeout_sec):
        observe(
            sensor.gateway,
            None,
            "gateway_offline",
            at,
            uuid.uuid5(projection.pk, at.isoformat() + "gateway"),
            {"freshness": projection.gateway_status},
            recovered=projection.gateway_status == "online",
        )


def evaluate_rejection(rejection):
    """Raise a gateway-scoped data-quality episode without trusting a rejected sensor identifier."""
    observe(
        rejection.gateway,
        None,
        "invalid_reading",
        rejection.received_at,
        rejection.pk,
        {"rejection": str(rejection.pk), "reason": rejection.reason},
    )
