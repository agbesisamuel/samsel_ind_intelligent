"""Local account mail only; asynchronous reset lookup avoids user-enumerating SMTP timing."""

import secrets
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from sii.audit.services import record

from .models import CustomUser, PasswordReset
from .security import token_digest


@shared_task(queue="notifications", ignore_result=True)
def send_password_reset(email):
    """Send only to a verified account via the configured local sink; reveal nothing to HTTP.

    Unknown addresses take the same enqueue path. A reset retains MFA, expires in
    30 minutes and never signs in. Task arguments/results must not be logged.
    """
    user = CustomUser.objects.filter(
        email=email.lower(), is_active=True, verified_at__isnull=False
    ).first()
    if user is None:
        return
    token = secrets.token_urlsafe(32)
    reset = PasswordReset.objects.create(
        user=user, token_hash=token_digest(token), expires_at=timezone.now() + timedelta(minutes=30)
    )
    try:
        send_mail(
            "SAMSEL local password reset / Nulstil adgangskode",
            f"Local synthetic development only.\n{settings.PORTAL_ORIGIN}/reset#token={token}",
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
        )
    except Exception:  # noqa: BLE001 — mail exceptions must never expose token-bearing content.
        reset.delete()
        record("password_reset.mail_failed", actor=user)
    else:
        record("password_reset.mail_accepted", actor=user)
