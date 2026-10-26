"""Server-computed quota/status and manual commercial changes with current explicit authority.

Only the subscription row is locked for capacity. No site/gateway row is acquired
after it, avoiding cycles with existing inventory lock ordering. SQL triggers use
the same authority and protect non-HTTP/bulk insertion. Existing monitoring paths
never consult commercial state, expiry or expansion quotas.
"""

from datetime import timedelta

from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from sii.assets.models import Sensor
from sii.audit.services import record
from sii.tenants.access import require_owner, scoped_org
from sii.tenants.models import Organisation, Site

from .models import InvoiceDraft, Plan, Subscription, SubscriptionChange


def commercial_org(user, identifier, platform_only=False):
    """Permit platform commercial metadata explicitly; never reuse this scope for site data."""
    if not user.is_active or not user.verified_at:
        raise PermissionDenied()
    if user.is_superuser:
        result = Organisation.objects.filter(pk=identifier).first()
        if result is None:
            raise NotFound()
        return result
    if platform_only:
        raise PermissionDenied()
    organisation = scoped_org(user, identifier)
    require_owner(user, organisation)
    return organisation


def usage(organisation_id):
    """Count unarchived sites and non-retired probes, including planned inventory."""
    return {
        "sites": Site.objects.filter(organisation_id=organisation_id, archived=False).count(),
        "sensors": Sensor.objects.filter(organisation_id=organisation_id)
        .exclude(state="retired")
        .count(),
    }


def can_expand(subscription, now=None):
    """Past-due/ended/expired terms block only new capacity, never existing safety evidence."""
    return subscription.state in {"trial", "pilot", "active", "ending"} and (
        subscription.ends_at is None or subscription.ends_at > (now or timezone.now())
    )


def ensure_capacity(organisation_id, kind, site_id=None):
    """Lock within the caller's transaction and reject expansion with a readable API error."""
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("Quota check requires the write transaction")
    subscription = (
        Subscription.objects.select_for_update(of=("self",))
        .select_related("plan")
        .filter(organisation_id=organisation_id)
        .first()
    )
    if not subscription or not can_expand(subscription):
        raise ValidationError("Plan configuration/term does not permit expansion.")
    counts = usage(organisation_id)
    if kind == "site":
        allowed = counts["sites"] < subscription.plan.max_sites
    elif kind == "sensor":
        local_count = (
            Sensor.objects.filter(organisation_id=organisation_id, site_id=site_id)
            .exclude(state="retired")
            .count()
        )
        allowed = (
            counts["sensors"] < subscription.plan.max_sensors
            and local_count < subscription.plan.max_sensors_per_site
        )
    else:
        raise ValueError("Unknown quota resource")
    if not allowed:
        raise ValidationError("Plan capacity reached; existing monitoring continues.")


def status(subscription):
    """Return metadata, expiry/overage warnings and explicit live-use boundaries."""
    counts = usage(subscription.organisation_id)
    now, warnings = timezone.now(), []
    if subscription.ends_at:
        if subscription.ends_at <= now:
            warnings.append("term_ended")
        elif subscription.ends_at - now <= timedelta(days=7):
            warnings.append("term_ends_within_7_days")
    per_site_over = (
        Sensor.objects.filter(organisation_id=subscription.organisation_id)
        .exclude(state="retired")
        .values("site_id")
        .annotate(n=Count("id"))
        .filter(n__gt=subscription.plan.max_sensors_per_site)
        .exists()
    )
    if (
        counts["sites"] > subscription.plan.max_sites
        or counts["sensors"] > subscription.plan.max_sensors
        or per_site_over
    ):
        warnings.append("over_quota_expansion_blocked")
    return {
        "plan": subscription.plan_id,
        "state": subscription.state,
        "starts_at": subscription.starts_at,
        "ends_at": subscription.ends_at,
        "billing_name": subscription.billing_name,
        "billing_email": subscription.billing_email,
        "purchase_reference": subscription.purchase_reference,
        "usage": counts,
        "limits": {
            "sites": subscription.plan.max_sites,
            "sensors": subscription.plan.max_sensors,
            "sensors_per_site": subscription.plan.max_sensors_per_site,
        },
        "warnings": warnings,
        "expansion_allowed": can_expand(subscription),
        "live_collections_enabled": False,
        "monitoring_suspended": False,
        "synthetic": True,
    }


def terms(subscription):
    """Canonical non-secret commercial change snapshot; exclude billing contact PII."""
    return {
        "plan": subscription.plan_id,
        "state": subscription.state,
        "ends_at": subscription.ends_at.isoformat() if subscription.ends_at else None,
    }


@transaction.atomic
def change(organisation, user, data):
    """Platform-only reviewed metadata change; a downgrade never retires existing assets."""
    if not user.is_superuser or not user.is_active or not user.verified_at:
        raise PermissionDenied()
    subscription = Subscription.objects.select_for_update().get(organisation=organisation)
    before = terms(subscription)
    plan = Plan.objects.filter(pk=data["plan"]).first()
    if not plan:
        raise ValidationError("Unknown configured plan")
    if data["ends_at"] and data["ends_at"] < subscription.starts_at:
        raise ValidationError("Term cannot end before its recorded start")
    subscription.plan, subscription.state, subscription.ends_at = (
        plan,
        data["state"],
        data["ends_at"],
    )
    subscription.save(update_fields=["plan", "state", "ends_at"])
    SubscriptionChange.objects.create(
        organisation=organisation,
        subscription=subscription,
        before=before,
        after=terms(subscription),
        reason=data["reason"],
        recorded_by=user,
    )
    record(
        "subscription.changed",
        actor=user,
        organisation=organisation,
        subject=subscription.pk,
        before=before,
        after=terms(subscription),
    )
    return subscription


@transaction.atomic
def invoice(organisation, user, data):
    """Idempotently preserve a manual draft; no external provider or collection is invoked."""
    if not user.is_superuser or not user.is_active or not user.verified_at:
        raise PermissionDenied()
    Subscription.objects.select_for_update().get(organisation=organisation)
    existing = InvoiceDraft.objects.filter(
        organisation=organisation, reference=data["reference"]
    ).first()
    if existing:
        if any(getattr(existing, key) != value for key, value in data.items()):
            raise ValidationError("Invoice reference already has different immutable content")
        return existing
    draft = InvoiceDraft.objects.create(organisation=organisation, recorded_by=user, **data)
    record("invoice.draft_recorded", actor=user, organisation=organisation, subject=draft.pk)
    return draft
