"""CSRF-protected invite-only session lifecycle with encrypted, replay-safe MFA."""

import secrets
import time

import pyotp
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.utils import extend_schema
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from sii.audit.services import record
from sii.tenants.models import Invitation, Membership, RoleAssignment

from .models import CustomUser, PasswordReset
from .security import (
    cipher,
    consume_totp,
    limit,
    requires_mfa,
    token_digest,
    valid_session,
)
from .serializers import AuthResult, CSRFResult, EmailInput, LoginInput, MFAInput, TokenInput
from .tasks import send_password_reset


def inputs(serializer_class, request):
    """Validate bounded input before any identity or token lookup."""
    serializer = serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def password_check(password, user):
    """Apply Django validators without echoing password contents in field errors."""
    try:
        validate_password(password, user)
    except DjangoValidationError as exc:
        raise ValidationError("Choose a stronger password.") from exc


def complete(request, user, mfa=False):
    """Rotate the session and bind it to the current identity security version."""
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session["auth_version"] = user.auth_version
    request.session["mfa_verified"] = mfa
    request.session["step_up_at"] = time.time() if mfa else 0
    request.session.pop("pending_user", None)
    request.session.pop("pending_at", None)
    request.session.pop("pending_version", None)
    request.session.set_expiry(8 * 60 * 60)
    record("auth.login", actor=user)
    return {"state": "complete"}


def challenge(request, user):
    """Password proof creates only a ten-minute pre-auth session, never a business login."""
    request.session.flush()
    request.session["pending_user"] = str(user.pk)
    request.session["pending_at"] = time.time()
    request.session["pending_version"] = user.auth_version
    request.session.set_expiry(600)
    return {"state": "mfa" if user.mfa_enabled else "enroll"}


def pending_user(request):
    """Lock the pre-auth identity; expiry/revocation cannot be bypassed with an old cookie."""
    age = time.time() - request.session.get("pending_at", 0)
    user = (
        CustomUser.objects.select_for_update()
        .filter(pk=request.session.get("pending_user"), is_active=True, verified_at__isnull=False)
        .first()
    )
    if (
        not user
        or not 0 <= age < 600
        or request.session.get("pending_version") != user.auth_version
    ):
        record("mfa.denied")
        raise PermissionDenied("Sign in again.")
    return user


@method_decorator(csrf_protect, name="dispatch")
class AuthView(APIView):
    """Anonymous auth commands still require CSRF; no bearer/device authentication is accepted."""

    permission_classes = [AllowAny]
    # Preserve existing Django identity for invite linking/re-authentication, while
    # permitting a revoked user to clear or replace their session through login.
    authentication_classes = [SessionAuthentication]

    def handle_exception(self, exc):
        """Record denied commands after their transaction unwinds, without request content."""
        response = super().handle_exception(exc)
        if 400 <= response.status_code < 500:
            record("auth.request_denied")
        return response

    def finalize_response(self, request, response, *args, **kwargs):
        """Prevent browsers/intermediaries caching identities, tokens or recovery material."""
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response


class CSRFView(AuthView):
    """Bootstrap same-origin CSRF without creating an authenticated session."""

    @extend_schema(responses=CSRFResult)
    def get(self, request):
        """Return the masked token; the browser receives the matching CSRF cookie."""
        return Response({"csrf_token": get_token(request)})


class LoginView(AuthView):
    """Verify password before challenging MFA, without revealing nonexistent accounts."""

    @extend_schema(request=LoginInput, responses=AuthResult)
    def post(self, request):
        """Throttle both IP and account; Django equalizes nonexistent-account password hashing."""
        data = inputs(LoginInput, request)
        email = data["email"].strip().lower()
        limit(request, "login", email)
        user = authenticate(request, email=email, password=data["password"])
        if not user or not user.verified_at:
            record("auth.denied")
            raise PermissionDenied("Invalid sign-in.")
        if requires_mfa(user) or user.mfa_enabled:
            return Response(challenge(request, user))
        return Response(complete(request, user))


class LogoutView(AuthView):
    """Destroy the current server session, including incomplete MFA challenges."""

    @extend_schema(request=None, responses=AuthResult)
    def post(self, request):
        """CSRF protects logout; unknown/revoked sessions can still be cleared safely."""
        record("auth.logout", actor=request._request.user)
        logout(request)
        return Response({"state": "signed_out"})


class AcceptInvitationView(AuthView):
    """Invitation possession proves email ownership, not authority over an existing account."""

    @extend_schema(request=TokenInput, responses=AuthResult)
    def post(self, request):
        """Consume once under lock; existing identities must already be fully authenticated."""
        data = inputs(TokenInput, request)
        limit(request, "invite_accept", maximum=10)
        with transaction.atomic():
            invitation = (
                Invitation.objects.select_for_update()
                .filter(
                    token_hash=token_digest(data["token"]),
                    accepted_at=None,
                    revoked_at=None,
                    expires_at__gt=timezone.now(),
                )
                .first()
            )
            if not invitation:
                raise ValidationError("Invalid or expired invitation.")
            user = CustomUser.objects.select_for_update().filter(email=invitation.email).first()
            if user:
                current = request._request.user
                if (
                    current.pk != user.pk
                    or not valid_session(request, current)
                    or not user.check_password(data["password"])
                ):
                    raise PermissionDenied("Sign in to the existing account before accepting.")
            else:
                user = CustomUser(email=invitation.email, verified_at=timezone.now())
                password_check(data["password"], user)
                user.set_password(data["password"])
                user.save()
            membership, _ = Membership.objects.get_or_create(
                organisation=invitation.organisation, user=user
            )
            if not membership.active:
                raise PermissionDenied("Membership is inactive.")
            RoleAssignment.objects.get_or_create(
                organisation=invitation.organisation,
                membership=membership,
                site=invitation.site,
                role=invitation.role,
            )
            invitation.accepted_at = timezone.now()
            invitation.save(update_fields=["accepted_at"])
            record(
                "invitation.accepted",
                actor=user,
                organisation=invitation.organisation,
                site=invitation.site,
                subject=invitation.pk,
            )
        if requires_mfa(user) or user.mfa_enabled:
            return Response(challenge(request, user))
        return Response(complete(request, user))


class ResetRequestView(AuthView):
    """Identical queued response for known and unknown emails; no account lookup in HTTP."""

    @extend_schema(request=EmailInput, responses=AuthResult)
    def post(self, request):
        """Send only through local SMTP asynchronously; rate-limit every submitted address."""
        data = inputs(EmailInput, request)
        limit(request, "password_reset", data["email"], maximum=5, seconds=1800)
        send_password_reset.delay(data["email"].strip().lower())
        return Response({"state": "accepted"}, status=202)


class ResetConfirmView(AuthView):
    """Reset passwords once, revoke all sessions/tokens, and retain MFA requirements."""

    @extend_schema(request=TokenInput, responses=AuthResult)
    def post(self, request):
        """Serialize token consumption with the user lock; never log in automatically."""
        data = inputs(TokenInput, request)
        limit(request, "reset_confirm")
        with transaction.atomic():
            candidate = PasswordReset.objects.filter(
                token_hash=token_digest(data["token"]),
                used_at=None,
                expires_at__gt=timezone.now(),
            ).first()
            if not candidate:
                raise ValidationError("Invalid or expired reset.")
            # Lock the identity first: two different tokens for one user must not
            # deadlock while each invalidates all sibling tokens. Recheck after locking.
            user = CustomUser.objects.select_for_update().get(pk=candidate.user_id)
            reset = (
                PasswordReset.objects.select_for_update()
                .filter(pk=candidate.pk, used_at=None, expires_at__gt=timezone.now())
                .first()
            )
            if not reset:
                raise ValidationError("Invalid or expired reset.")
            password_check(data["password"], user)
            user.set_password(data["password"])
            user.auth_version += 1
            user.save(update_fields=["password", "auth_version"])
            PasswordReset.objects.filter(user=user, used_at=None).update(used_at=timezone.now())
            record("password.reset", actor=user)
        logout(request)
        return Response({"state": "signed_out"})


class MFAEnrollView(AuthView):
    """Return a new TOTP secret only after password proof; never overwrite an enabled factor."""

    @extend_schema(request=MFAInput, responses=AuthResult)
    def post(self, request):
        """Encrypt the seed and require a correct code before enabling MFA or login."""
        data = inputs(MFAInput, request)
        limit(request, "enroll", maximum=5)
        with transaction.atomic():
            current = request._request.user
            if valid_session(request, current):
                if not current.check_password(data["password"]):
                    raise PermissionDenied()
                challenge(request, current)
            user = pending_user(request)
            if user.mfa_enabled:
                raise PermissionDenied("Use the recovery flow to replace an enabled factor.")
            secret = pyotp.random_base32()
            user.mfa_secret = cipher().encrypt(secret.encode()).decode()
            user.mfa_last_counter = -1
            user.save(update_fields=["mfa_secret", "mfa_last_counter"])
            record("mfa.enrollment_started", actor=user)
        return Response(
            {
                "state": "enroll",
                "secret": secret,
                "provisioning_uri": pyotp.TOTP(secret).provisioning_uri(
                    user.email, issuer_name="SAMSEL local"
                ),
            }
        )


class MFAVerifyView(AuthView):
    """Verify a replay-safe factor, or consume a recovery code and require fresh enrolment."""

    @extend_schema(request=MFAInput, responses=AuthResult)
    def post(self, request):
        """One-time recovery needs password proof and never bypasses factor replacement."""
        data = inputs(MFAInput, request)
        limit(request, "mfa", request.session.get("pending_user", ""), maximum=5)
        with transaction.atomic():
            user = pending_user(request)
            hashed = token_digest(data["code"])
            if user.mfa_enabled and hashed in user.recovery_hashes:
                user.mfa_enabled = False
                user.mfa_secret = ""
                user.recovery_hashes = []
                user.auth_version += 1
                user.save()
                record("mfa.recovery_used", actor=user)
                return Response(challenge(request, user))
            if not consume_totp(user, data["code"]):
                record("mfa.denied", actor=user)
                # Return instead of raising: retain denied audit evidence in this transaction.
                return Response(
                    {
                        "code": "mfa_denied",
                        "message": "Invalid proof.",
                        "details": {},
                        "request_id": request.request_id,
                    },
                    status=403,
                )
            recovery = None
            if not user.mfa_enabled:
                recovery = [secrets.token_urlsafe(24) for _ in range(8)]
                user.mfa_enabled = True
                user.recovery_hashes = [token_digest(code) for code in recovery]
                user.save(update_fields=["mfa_enabled", "recovery_hashes"])
                record("mfa.enabled", actor=user)
            result = complete(request, user, mfa=True)
            if recovery:
                result["recovery_codes"] = recovery
            return Response(result)


class StepUpView(AuthView):
    """Fresh password and unused TOTP proof authorizes high-risk changes for five minutes."""

    @extend_schema(request=MFAInput, responses=AuthResult)
    def post(self, request):
        """Never accept a recovery code as direct step-up; recovery requires reenrollment."""
        data = inputs(MFAInput, request)
        limit(request, "step_up", maximum=5)
        current = request._request.user
        if not valid_session(request, current):
            raise PermissionDenied()
        with transaction.atomic():
            user = CustomUser.objects.select_for_update().get(pk=current.pk)
            if not user.check_password(data["password"]) or not consume_totp(user, data["code"]):
                record("step_up.denied", actor=user)
                return Response(
                    {
                        "code": "step_up_denied",
                        "message": "Invalid proof.",
                        "details": {},
                        "request_id": request.request_id,
                    },
                    status=403,
                )
            request.session["step_up_at"] = time.time()
            request.session["mfa_verified"] = True
            record("step_up.verified", actor=user)
        return Response({"state": "complete"})
