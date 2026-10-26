"""Session assurance, replay-safe encrypted TOTP and atomic brute-force limits."""

import base64
import hashlib
import secrets
import time
from datetime import timedelta

import pyotp
from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone
from drf_spectacular.authentication import SessionScheme
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied, Throttled
from rest_framework.permissions import BasePermission

from sii.audit.services import record
from sii.tenants.access import PRIVILEGED_ROLES, assignments

from .models import AuthRateBucket


class VerifiedSessionScheme(SessionScheme):
    """Document the cookie scheme; live authentication also checks verification and MFA."""

    target_class = "sii.accounts.security.VerifiedSessionAuthentication"
    name = "verifiedSession"


def token_digest(value):
    """Hash high-entropy one-time tokens; never store their bearer representation."""
    return hashlib.sha256(value.encode()).hexdigest()


def cipher():
    """Decode a separately generated encryption key; missing configuration fails closed."""
    try:
        raw = bytes.fromhex(settings.MFA_ENCRYPTION_KEY)
        if len(raw) != 32:
            raise ValueError()
        return Fernet(base64.urlsafe_b64encode(raw))
    except ValueError as exc:
        raise ImproperlyConfigured("Run setup to create the MFA encryption key.") from exc


def requires_mfa(user):
    """Enforce MFA dynamically after role elevation, including all platform staff."""
    return (
        user.is_staff
        or user.is_superuser
        or assignments(user).filter(role__in=PRIVILEGED_ROLES).exists()
    )


def valid_session(request, user):
    """Check live identity/version/assurance; privilege changes cannot bless older sessions."""
    return bool(
        user.is_authenticated
        and user.is_active
        and user.verified_at
        and request.session.get("auth_version") == user.auth_version
        and (
            not (requires_mfa(user) or user.mfa_enabled)
            or (user.mfa_enabled and request.session.get("mfa_verified") is True)
        )
    )


class VerifiedSessionAuthentication(SessionAuthentication):
    """Keep Django CSRF semantics and reject revoked or insufficient-assurance sessions."""

    def authenticate(self, request):
        """Never accept a device token, incomplete MFA challenge or old security version."""
        result = super().authenticate(request)
        if result and not valid_session(request, result[0]):
            record("session.denied", actor=result[0])
            raise PermissionDenied("Complete authentication again.")
        return result


class VerifiedUser(BasePermission):
    """Explicit opt-in for implemented business endpoints; default permission stays deny-all."""

    def has_permission(self, request, view):
        """Require a valid session; object services must still enforce exact scope."""
        return valid_session(request, request.user)


def step_up(request):
    """Require a fresh password-plus-TOTP proof before any privileged administration."""
    age = time.time() - request.session.get("step_up_at", 0)
    if (
        not valid_session(request, request.user)
        or not request.session.get("mfa_verified")
        or not 0 <= age <= 300
    ):
        record("step_up.denied", actor=request.user)
        raise PermissionDenied("Recent password and MFA confirmation required.")


def consume_totp(user, code):
    """Consume a new ±1-window TOTP counter; callers must lock the user row transactionally."""
    if not user.mfa_secret or len(code) != 6 or not code.isascii() or not code.isdecimal():
        return False
    totp = pyotp.TOTP(cipher().decrypt(user.mfa_secret.encode()).decode())
    counter = int(time.time()) // 30
    for candidate in [counter, counter - 1, counter + 1]:
        if candidate > user.mfa_last_counter and secrets.compare_digest(
            totp.at(candidate * 30), code
        ):
            user.mfa_last_counter = candidate
            user.save(update_fields=["mfa_last_counter"])
            return True
    return False


def limit(request, action, identity="", maximum=10, seconds=60):
    """Count attempts atomically by IP and optional account; never trust proxy headers.

    Rows expire logically with each fixed window. A bounded cleanup deletes only
    expired counters, never audit evidence. PostgreSQL locking avoids cache races.
    """
    now = timezone.now()
    expired = list(
        AuthRateBucket.objects.filter(expires_at__lt=now).values_list("key", flat=True)[:100]
    )
    AuthRateBucket.objects.filter(key__in=expired).delete()
    window = int(now.timestamp()) // seconds
    subjects = [request.META.get("REMOTE_ADDR", "unknown")]
    if identity:
        subjects.append(identity.lower())
    denied = False
    for subject in subjects:
        key = token_digest(f"{action}:{subject}:{window}")
        with transaction.atomic():
            AuthRateBucket.objects.get_or_create(
                key=key, defaults={"expires_at": now + timedelta(seconds=seconds * 2)}
            )
            bucket = AuthRateBucket.objects.select_for_update().get(pk=key)
            bucket.count += 1
            bucket.save(update_fields=["count"])
            denied |= bucket.count > maximum
    if denied:
        record("auth.throttled")
        raise Throttled(wait=seconds)
