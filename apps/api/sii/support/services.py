"""Narrow support capability with current owner/staff verification, expiry and audited reads."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from sii.audit.services import record
from sii.incidents.models import Incident
from sii.notifications.models import Notification
from sii.reports.models import ReportJob
from sii.tenants.access import is_owner, require_owner

from .models import SupportAccessLog, SupportSession


@transaction.atomic
def approve(user, site, supporter, minutes, reason):
    """Require an independent verified staff identity and bounded owner-approved purpose."""
    require_owner(user, site.organisation)
    if not supporter.is_active or not supporter.is_staff or not supporter.verified_at:
        raise NotFound()
    if supporter == user or not 1 <= minutes <= 60 or not 8 <= len(reason) <= 500:
        raise ValidationError("Use independent support identity, 1..60 minutes and a reason.")
    session = SupportSession.objects.create(
        organisation=site.organisation,
        site=site,
        supporter=supporter,
        approved_by=user,
        reason=reason,
        expires_at=timezone.now() + timedelta(minutes=minutes),
    )
    record(
        "support.approved",
        actor=user,
        organisation=site.organisation,
        site=site,
        subject=session.pk,
        after={"scope": "diagnostics", "minutes": minutes},
    )
    return session


@transaction.atomic
def revoke(user, session):
    """Owners can immediately end access without changing the original approval record."""
    require_owner(user, session.organisation)
    session = SupportSession.objects.select_for_update().get(pk=session.pk)
    if session.revoked_at is None:
        session.revoked_at = timezone.now()
        session.save()
        record(
            "support.revoked",
            actor=user,
            organisation=session.organisation,
            site=session.site,
            subject=session.pk,
        )
    return session


@transaction.atomic
def diagnostics(user, identifier):
    """Read diagnostic counts only, excluding raw data, identities, files and device controls.

    The lock serializes revocation with access. Losing staff status, approval-owner
    authority or the deadline invalidates this capability immediately on the next read.
    HTTP additionally requires a recent MFA step-up for the support user's own session.
    """
    session = (
        SupportSession.objects.select_for_update()
        .filter(
            pk=identifier,
            supporter=user,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
            scope="diagnostics",
        )
        .first()
    )
    if not session or not user.is_active or not user.is_staff or not user.verified_at:
        raise NotFound()
    if not is_owner(session.approved_by, session.organisation):
        raise NotFound()
    SupportAccessLog.objects.create(
        organisation=session.organisation,
        site=session.site,
        session=session,
        action="diagnostics.read",
    )
    record(
        "support.accessed",
        actor=user,
        organisation=session.organisation,
        site=session.site,
        subject=session.pk,
    )
    return {
        "site": str(session.site_id),
        "scope": session.scope,
        "unresolved_incidents": Incident.objects.filter(site=session.site)
        .exclude(status="closed")
        .count(),
        "failed_notifications": Notification.objects.filter(
            site=session.site, status__in=["dead", "uncertain"]
        ).count(),
        "failed_reports": ReportJob.objects.filter(site=session.site, status="failed").count(),
    }
