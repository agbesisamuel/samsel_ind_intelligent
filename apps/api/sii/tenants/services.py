"""Transactional tenant commands shared by API and local bootstrap tooling."""

import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from sii.accounts.security import token_digest
from sii.audit.services import record

from .models import Invitation


def send_invitation(invitation, token):
    """Send a bilingual local-only proof link after commit; never print a token on failure."""
    try:
        send_mail(
            "SAMSEL invitation / Invitation",
            "Local synthetic development only / Kun lokal udvikling.\n"
            f"{settings.PORTAL_ORIGIN}/accept#token={token}",
            settings.DEFAULT_FROM_EMAIL,
            [invitation.email],
        )
    except Exception:  # noqa: BLE001 — suppress mail exceptions that can contain bearer URLs.
        record(
            "invitation.mail_failed", organisation=invitation.organisation, subject=invitation.pk
        )
    else:
        record(
            "invitation.mail_accepted", organisation=invitation.organisation, subject=invitation.pk
        )


@transaction.atomic
def issue_invitation(organisation, email, role, site=None, actor=None):
    """Persist a digest, expire after 48 hours and deliver only through the local SMTP sink.

    API callers must authorize the exact offered scope before invoking this service.
    The local bootstrap command is the only non-HTTP caller; model and DB guards
    still reject a site from another organisation.
    """
    token = secrets.token_urlsafe(32)
    invitation = Invitation.objects.create(
        organisation=organisation,
        email=email.strip().lower(),
        role=role,
        site=site,
        invited_by=actor,
        token_hash=token_digest(token),
        expires_at=timezone.now() + timedelta(hours=48),
    )
    record(
        "invitation.created",
        actor=actor,
        organisation=organisation,
        site=site,
        subject=invitation.pk,
        after={"role": role, "site": site.pk if site else None},
    )
    transaction.on_commit(lambda: send_invitation(invitation, token))
    return invitation
