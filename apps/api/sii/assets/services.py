"""Shared inventory scope, qualification and lifecycle commands; no activation shortcuts."""

import json
from types import SimpleNamespace

from django.conf import settings
from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from sii.accounts.security import step_up
from sii.audit.services import digest, record
from sii.tenants.access import assignments, sites_for
from sii.tenants.models import Role, Site

from .models import (
    CalibrationRecord,
    CommissioningAcceptance,
    Lifecycle,
    Sensor,
    SensorCommissioning,
    SiteCommissioning,
)


def scoped_site(user, organisation_id, site_id, write=False):
    """Resolve exact active user scope for APIs/workers without a staff bypass."""
    site = (
        sites_for(user, organisation_id, [Role.SITE_ADMIN] if write else None)
        .filter(pk=site_id)
        .first()
    )
    if site is None:
        record("inventory.scope_denied", actor=user)
        raise NotFound()
    return site


def require_qa(user, site):
    """QA authority is explicit at the site; ownership or platform status does not imply it."""
    if (
        not assignments(user)
        .filter(organisation=site.organisation, site=site, role=Role.QA)
        .exists()
    ):
        record("commissioning.qa_denied", actor=user, organisation=site.organisation, site=site)
        raise PermissionDenied()


def qualified_query(query, at=None):
    """Fetch current evidence and hierarchy in one scoped query, without cross-request caching.

    Correlated latest-record subqueries retain expiry/amendment ordering exactly. This
    prevents a 40-probe rule check from issuing hundreds of per-probe SQL round trips.
    Callers taking locks must use select_for_update(of=('self',)) to preserve lock order.
    """
    now = at or timezone.now()
    calibration = CalibrationRecord.objects.filter(
        sensor_id=OuterRef("pk"), checked_at__lte=now
    ).order_by("-checked_at", "-id")
    installation = SensorCommissioning.objects.filter(sensor_id=OuterRef("pk")).order_by(
        "-recorded_at", "-id"
    )
    fields = {
        "_cal_" + name: Subquery(calibration.values(name)[:1])
        for name in ["id", "due_at", "synthetic"]
    }
    fields.update(
        {
            "_placement_" + name: Subquery(installation.values(name)[:1])
            for name in ["id", "read_only_scope", "synthetic"]
        }
    )
    return query.select_related("gateway", "zone__building", "site").annotate(**fields)


def sensor_qualification(sensor, at=None):
    """Calculate current warnings from preserved evidence; absence/expiry is never safe/green."""
    now = at or timezone.now()
    if hasattr(sensor, "_cal_id"):
        calibration = (
            SimpleNamespace(
                pk=sensor._cal_id, due_at=sensor._cal_due_at, synthetic=sensor._cal_synthetic
            )
            if sensor._cal_id
            else None
        )
        installation = (
            SimpleNamespace(
                pk=sensor._placement_id,
                read_only_scope=sensor._placement_read_only_scope,
                synthetic=sensor._placement_synthetic,
            )
            if sensor._placement_id
            else None
        )
    else:
        calibration = (
            sensor.calibrations.filter(checked_at__lte=now).order_by("-checked_at", "-id").first()
        )
        installation = sensor.commissionings.order_by("-recorded_at", "-id").first()
    calibration_state = (
        "unknown"
        if calibration is None
        else "expired"
        if calibration.due_at <= now
        else "synthetic_valid"
        if calibration.synthetic
        else "valid"
    )
    warnings = []
    if calibration_state in ["unknown", "expired"]:
        warnings.append("calibration_" + calibration_state)
    if not installation or not installation.read_only_scope:
        warnings.append("placement_unqualified")
    if sensor.state == Lifecycle.RETIRED or sensor.gateway.state == Lifecycle.RETIRED:
        warnings.append("device_retired")
    if sensor.state == Lifecycle.PLANNED or sensor.gateway.state == Lifecycle.PLANNED:
        warnings.append("device_not_commissioning")
    if sensor.zone.archived or sensor.zone.building.archived or sensor.site.archived:
        warnings.append("facility_archived")
    return {
        "calibration_status": calibration_state,
        "calibration_due_at": calibration.due_at if calibration else None,
        "calibration_id": calibration.pk if calibration else None,
        "installation_id": installation.pk if installation else None,
        "warnings": warnings,
        "synthetic": True if installation is None else installation.synthetic,
    }


def pack_evidence(pack):
    """Create a deterministic current snapshot and missing-precondition list for QA review."""
    warnings = []
    if not pack.read_only_scope:
        warnings.append("read_only_scope_missing")
    if not pack.customer_approval_reference:
        warnings.append("customer_reference_missing")
    if not pack.contingency_reference:
        warnings.append("contingency_missing")
    tests = {}
    for kind in ["sensor_feed", "breach", "no_data", "routing"]:
        latest = pack.tests.filter(kind=kind).order_by("-recorded_at", "-id").first()
        tests[kind] = str(latest.pk) if latest else None
        if not latest or not latest.passed:
            warnings.append(kind + "_test_missing_or_failed")
    sensors = (
        Sensor.objects.filter(organisation=pack.organisation, site=pack.site)
        .exclude(state=Lifecycle.RETIRED)
        .order_by("id")
    )
    states = {
        str(sensor.pk): {
            **sensor_qualification(sensor),
            "zone": str(sensor.zone_id),
            "gateway": str(sensor.gateway_id),
            "state": sensor.state,
            "unit": sensor.unit,
            "expected_interval_sec": sensor.expected_interval_sec,
            "engineering_min": sensor.engineering_min,
            "engineering_max": sensor.engineering_max,
            "capability_reference": sensor.capability_reference,
            "sop_reference": sensor.zone.sop_reference,
        }
        for sensor in sensors
    }
    if not states:
        warnings.append("no_sensors")
    if any(state["warnings"] for state in states.values()):
        warnings.append("sensor_qualification_missing")
    evidence = {"pack": str(pack.pk), "tests": tests, "sensors": states}
    # Normalize dates/UUIDs once so the stored snapshot and canonical digest reproduce exactly.
    evidence = json.loads(json.dumps(evidence, default=str))
    return evidence, warnings


@transaction.atomic
def accept_pack(request, site, pack_id):
    """Require fresh QA proof and current evidence; acceptance remains explicitly synthetic."""
    require_qa(request.user, site)
    step_up(request)
    Site.objects.select_for_update().get(pk=site.pk)
    pack = SiteCommissioning.objects.filter(
        pk=pack_id, organisation=site.organisation, site=site
    ).first()
    if not pack:
        raise NotFound()
    evidence, warnings = pack_evidence(pack)
    if warnings:
        raise ValidationError("Commissioning evidence is incomplete.")
    acceptance = CommissioningAcceptance.objects.create(
        organisation=site.organisation,
        site=site,
        commissioning=pack,
        approved_by=request.user,
        evidence_hash=digest(evidence),
        evidence_snapshot=evidence,
        synthetic=True,
    )
    record(
        "commissioning.synthetic_accepted",
        actor=request.user,
        organisation=site.organisation,
        site=site,
        subject=acceptance.pk,
        after={"evidence_hash": acceptance.evidence_hash},
    )
    return acceptance


def activation_gaps(site):
    """Return blockers until verified rules, routes and real approval exist."""
    gaps = ["approved_rule_versions_required", "verified_notification_routes_required"]
    if settings.ENVIRONMENT in {"local", "test"}:
        gaps.append("synthetic_environment_cannot_activate_live_monitoring")
    if not CommissioningAcceptance.objects.filter(
        site=site, organisation=site.organisation, synthetic=False
    ).exists():
        gaps.append("real_customer_qa_acceptance_required")
    return gaps


@transaction.atomic
def transition(request, site, model, object_id, target):
    """Audit lifecycle changes; retirement is terminal and live activation fails closed."""
    step_up(request)
    Site.objects.select_for_update().get(pk=site.pk)
    obj = model.objects.filter(pk=object_id, organisation=site.organisation, site=site).first()
    if not obj:
        raise NotFound()
    allowed = {
        Lifecycle.PLANNED: {Lifecycle.COMMISSIONING, Lifecycle.RETIRED},
        Lifecycle.COMMISSIONING: {Lifecycle.ACTIVE, Lifecycle.DEGRADED, Lifecycle.RETIRED},
        Lifecycle.ACTIVE: {Lifecycle.DEGRADED, Lifecycle.RETIRED},
        Lifecycle.DEGRADED: {Lifecycle.COMMISSIONING, Lifecycle.ACTIVE, Lifecycle.RETIRED},
        Lifecycle.RETIRED: set(),
    }
    if target not in allowed[obj.state]:
        raise ValidationError("Invalid lifecycle transition.")
    if target == Lifecycle.ACTIVE and activation_gaps(site):
        raise ValidationError("Monitoring activation preconditions are not satisfied.")
    before = obj.state
    obj.state = target
    obj.save(update_fields=["state"])
    record(
        "inventory.lifecycle_changed",
        actor=request.user,
        organisation=site.organisation,
        site=site,
        subject=obj.pk,
        before=before,
        after=target,
    )
    return obj
