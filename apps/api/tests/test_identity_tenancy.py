"""Release-blocking T-09/T-22 matrix: real sessions, CSRF, MFA and PostgreSQL scope guards."""

import secrets
import time
from datetime import timedelta
from unittest.mock import patch

import pyotp
import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from sii.accounts.models import AuthRateBucket, CustomUser, PasswordReset
from sii.accounts.security import cipher, token_digest
from sii.audit.models import AuditEvent
from sii.audit.services import digest, record
from sii.tenants.access import sites_for
from sii.tenants.models import Invitation, Membership, Role, RoleAssignment, Site

pytestmark = pytest.mark.django_db


def post(client, url, data=None, method="post"):
    """Exercise real CSRF middleware on every unsafe request, including anonymous auth."""
    csrf = client.get("/api/v1/auth/csrf/").json()["csrf_token"]
    return getattr(client, method)(url, data or {}, format="json", HTTP_X_CSRFTOKEN=csrf)


def sign_in(user, password, mfa=True):
    """Complete password and real TOTP enrollment through the API; never force-authenticate."""
    client = APIClient(enforce_csrf_checks=True)
    result = post(client, "/api/v1/auth/login/", {"email": user.email, "password": password})
    assert result.status_code == 200, result.content
    secret = None
    recovery = None
    if result.json()["state"] == "enroll" and mfa:
        result = post(client, "/api/v1/auth/mfa/enroll/")
        assert result.status_code == 200, result.content
        secret = result.json()["secret"]
        result = post(client, "/api/v1/auth/mfa/verify/", {"code": pyotp.TOTP(secret).now()})
        assert result.status_code == 200, result.content
        recovery = result.json()["recovery_codes"]
    return client, secret, recovery


def root(org):
    """Use implemented organisation nesting consistently in all negative matrix cases."""
    return f"/api/v1/organisations/{org.pk}/"


@pytest.mark.parametrize("suffix", ["", "sites/", "members/", "invitations/", "audit/"])
def test_t09_foreign_collections_and_objects_denied(world, suffix):
    """A real A-owner session cannot read any B collection, counts or metadata by guessed URL."""
    client, _, _ = sign_in(world["a"]["user"], world["password"])
    response = client.get(root(world["b"]["org"]) + suffix)
    assert response.status_code == 404
    assert b"Fictional b" not in response.content


def test_t09_nested_site_and_body_tenant_spoofing(world):
    """Nested B IDs and mass-assignment organisation/service-state overrides cannot cross scope."""
    client, _, _ = sign_in(world["a"]["user"], world["password"])
    base = root(world["a"]["org"])
    foreign = world["b"]["sites"][0]
    assert client.get(base + f"sites/{foreign.pk}/").status_code == 404
    assert (
        post(
            client, base + "sites/", {"name": "bad", "organisation": str(foreign.organisation_id)}
        ).status_code
        == 400
    )
    assert (
        post(client, base + "sites/", {"name": "bad", "service_state": "active"}).status_code == 400
    )
    assert (
        post(
            client,
            base + "roles/",
            {
                "membership_id": str(world["b"]["member"].pk),
                "site_id": str(world["a"]["sites"][0].pk),
                "role": "qa",
            },
        ).status_code
        == 404
    )
    assert (
        post(
            client,
            base + "invitations/",
            {"email": "new@example.invalid", "site_id": str(foreign.pk), "role": "operator"},
        ).status_code
        == 404
    )


def test_site_scopes_and_background_service_are_identical(world):
    """An operator sees only assigned A1 in API and service calls, even with B query filters."""
    a = world["a"]
    RoleAssignment.objects.filter(membership=a["member"]).delete()
    RoleAssignment.objects.create(
        organisation=a["org"], membership=a["member"], role=Role.OPERATOR, site=a["sites"][0]
    )
    client, _, _ = sign_in(a["user"], world["password"])
    result = client.get(root(a["org"]) + "sites/", {"organisation_id": str(world["b"]["org"].pk)})
    assert [row["id"] for row in result.json()["results"]] == [str(a["sites"][0].pk)]
    assert client.get(root(a["org"]) + f"sites/{a['sites'][1].pk}/").status_code == 404
    assert list(sites_for(a["user"], a["org"].pk)) == [a["sites"][0]]
    assert not sites_for(a["user"], world["b"]["org"].pk).exists()
    assert client.get(root(a["org"]) + "members/").json()["count"] == 0


def test_platform_admin_has_no_customer_site_access(world):
    """Explicit provisioning metadata access must never imply membership or site-data access."""
    admin = CustomUser.objects.create_superuser(
        "platform@example.invalid", world["password"], verified_at=timezone.now()
    )
    client, _, _ = sign_in(admin, world["password"])
    assert client.get("/api/v1/organisations/").json()["count"] == 2
    assert client.get(root(world["a"]["org"]) + "sites/").status_code == 404


def test_t22_incomplete_mfa_and_stale_step_up_denied(world):
    """Password-only privileged sessions cannot read data; stale step-up cannot mutate roles."""
    user = world["a"]["user"]
    client, _, _ = sign_in(user, world["password"], mfa=False)
    assert client.get("/api/v1/me/").status_code == 403
    assert post(client, "/api/v1/auth/mfa/verify/", {"code": "000000"}).status_code == 403
    client, _, _ = sign_in(user, world["password"])
    session = client.session
    session["step_up_at"] = time.time() - 301
    session.save()
    assert (
        post(client, root(world["a"]["org"]) + "sites/", {"name": "not created"}).status_code == 403
    )
    assert AuditEvent.objects.filter(action="step_up.denied").exists()


def test_totp_replay_and_revoked_session_denied(world):
    """A consumed TOTP cannot refresh assurance; auth-version changes revoke server sessions."""
    user = world["a"]["user"]
    client, secret, _ = sign_in(user, world["password"])
    user.refresh_from_db()
    code = pyotp.TOTP(secret).at(user.mfa_last_counter * 30)
    assert (
        post(
            client, "/api/v1/auth/step-up/", {"password": world["password"], "code": code}
        ).status_code
        == 403
    )
    user.auth_version += 1
    user.save()
    assert client.get("/api/v1/me/").status_code == 403
    assert post(client, "/api/v1/auth/logout/").status_code == 200


def test_recovery_is_single_use_requires_password_and_reenrollment(world):
    """Recovery never becomes a direct privileged session or a repeatable factor-reset backdoor."""
    user = world["a"]["user"]
    client, secret, recovery = sign_in(user, world["password"])
    user.refresh_from_db()
    assert secret not in user.mfa_secret
    assert cipher().decrypt(user.mfa_secret.encode()).decode() == secret
    assert recovery[0] not in user.recovery_hashes
    post(client, "/api/v1/auth/logout/")
    assert post(client, "/api/v1/auth/mfa/verify/", {"code": recovery[0]}).status_code == 403
    post(client, "/api/v1/auth/login/", {"email": user.email, "password": world["password"]})
    response = post(client, "/api/v1/auth/mfa/verify/", {"code": recovery[0]})
    assert response.json()["state"] == "enroll"
    assert client.get("/api/v1/me/").status_code == 403
    assert post(client, "/api/v1/auth/mfa/verify/", {"code": recovery[0]}).status_code == 403
    user.refresh_from_db()
    assert not user.mfa_enabled and not user.recovery_hashes


@pytest.mark.parametrize("expired", [True, False])
def test_invitation_expiry_and_replay(world, expired):
    """A verified invitation creates exactly one scoped membership; expired/reused proofs fail."""
    token = secrets.token_urlsafe(32)
    a = world["a"]
    invite = Invitation.objects.create(
        organisation=a["org"],
        invited_by=a["user"],
        email="invited@example.invalid",
        role=Role.OPERATOR,
        site=a["sites"][0],
        token_hash=token_digest(token),
        expires_at=timezone.now() + timedelta(hours=-1 if expired else 1),
    )
    client = APIClient(enforce_csrf_checks=True)
    data = {"token": token, "password": secrets.token_urlsafe(32)}
    first = post(client, "/api/v1/auth/invitations/accept/", data)
    assert first.status_code == (400 if expired else 200)
    assert post(client, "/api/v1/auth/invitations/accept/", data).status_code == 400
    invite.refresh_from_db()
    assert bool(invite.accepted_at) is not expired
    assert token not in str(Invitation.objects.values().get(pk=invite.pk))


def test_existing_account_invitation_cannot_reset_password(world):
    """Possession of a new invitation is not a password-reset or existing MFA bypass."""
    token = secrets.token_urlsafe(32)
    b = world["b"]
    Invitation.objects.create(
        organisation=world["a"]["org"],
        invited_by=world["a"]["user"],
        email=b["user"].email,
        role=Role.OWNER,
        token_hash=token_digest(token),
        expires_at=timezone.now() + timedelta(hours=1),
    )
    response = post(
        APIClient(enforce_csrf_checks=True),
        "/api/v1/auth/invitations/accept/",
        {"token": token, "password": world["password"]},
    )
    assert response.status_code == 403
    assert Membership.objects.filter(user=b["user"]).count() == 1


def test_password_reset_request_does_not_enumerate(world):
    """Known and unknown addresses follow identical HTTP/queue paths without synchronous lookup."""
    client = APIClient(enforce_csrf_checks=True)
    with patch("sii.accounts.views.send_password_reset.delay") as task:
        known = post(
            client, "/api/v1/auth/password-reset/request/", {"email": world["a"]["user"].email}
        )
        unknown = post(
            client, "/api/v1/auth/password-reset/request/", {"email": "absent@example.invalid"}
        )
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json() == {"state": "accepted"}
    assert task.call_count == 2


def test_reset_revokes_sessions_is_single_use_and_retains_mfa(world):
    """Password reset cannot be replayed or turn off an enabled second factor."""
    user = world["a"]["user"]
    client, _, _ = sign_in(user, world["password"])
    token = secrets.token_urlsafe(32)
    PasswordReset.objects.create(
        user=user, token_hash=token_digest(token), expires_at=timezone.now() + timedelta(minutes=30)
    )
    anonymous = APIClient(enforce_csrf_checks=True)
    data = {"token": token, "password": secrets.token_urlsafe(32)}
    assert post(anonymous, "/api/v1/auth/password-reset/confirm/", data).status_code == 200
    assert post(anonymous, "/api/v1/auth/password-reset/confirm/", data).status_code == 400
    assert client.get("/api/v1/me/").status_code == 403
    user.refresh_from_db()
    assert user.mfa_enabled


@pytest.mark.parametrize(
    "endpoint",
    [
        "login",
        "logout",
        "mfa/enroll",
        "mfa/verify",
        "step-up",
        "invitations/accept",
        "password-reset/request",
        "password-reset/confirm",
    ],
)
def test_csrf_is_required_even_before_authentication(endpoint):
    """DRF's anonymous-session exemption must not expose login or token-consumption CSRF."""
    client = APIClient(enforce_csrf_checks=True)
    assert client.post(f"/api/v1/auth/{endpoint}/", {}, format="json").status_code == 403


def test_login_throttling_is_atomic_and_does_not_store_raw_identifiers(world, monkeypatch):
    """Rate bounds apply to invalid credentials and store only hashed account/IP keys."""
    # A fixed window removes dependence on the wall clock crossing a throttle boundary.
    fixed_now = timezone.now().replace(second=10, microsecond=0)
    monkeypatch.setattr("sii.accounts.security.timezone.now", lambda: fixed_now)
    client = APIClient(enforce_csrf_checks=True)
    for _ in range(10):
        assert (
            post(
                client,
                "/api/v1/auth/login/",
                {"email": "absent@example.invalid", "password": "incorrect"},
            ).status_code
            == 403
        )
    assert (
        post(
            client,
            "/api/v1/auth/login/",
            {"email": "absent@example.invalid", "password": "incorrect"},
        ).status_code
        == 429
    )
    assert all(len(key) == 64 for key in AuthRateBucket.objects.values_list("key", flat=True))


def test_database_guards_reject_bulk_cross_tenant_relations_and_transfer(world):
    """ORM bypasses still cannot transfer tenant ownership or attach a foreign membership/site."""
    a, b = world["a"], world["b"]
    with pytest.raises(ValidationError):
        RoleAssignment.objects.create(
            organisation=a["org"], membership=b["member"], role=Role.OWNER
        )
    for member, site in [(b["member"], a["sites"][0]), (a["member"], b["sites"][0])]:
        with pytest.raises(IntegrityError), transaction.atomic():
            RoleAssignment.objects.bulk_create(
                [
                    RoleAssignment(
                        organisation=a["org"], membership=member, role=Role.OPERATOR, site=site
                    )
                ]
            )
    with pytest.raises(IntegrityError), transaction.atomic():
        Site.objects.filter(pk=a["sites"][0].pk).update(organisation=b["org"])


def test_audit_chain_hashes_and_mutation_protection(world):
    """Audit appends form a verifiable chain; update/delete fail even through QuerySet bypasses."""
    a = world["a"]
    first = record("test.created", actor=a["user"], organisation=a["org"], subject=a["org"].pk)
    second = record(
        "test.updated", actor=a["user"], organisation=a["org"], before={"role": "operator"}
    )
    assert second.prev_hash == first.event_hash
    assert second.sequence == first.sequence + 1
    fields = {
        field: getattr(second, field)
        for field in [
            "organisation_id",
            "site_id",
            "actor_id",
            "action",
            "subject",
            "occurred_at",
            "sequence",
            "before_hash",
            "after_hash",
            "prev_hash",
        ]
    }
    assert second.event_hash == digest(fields)
    with pytest.raises(IntegrityError), transaction.atomic():
        AuditEvent.objects.filter(pk=first.pk).update(action="tampered")
    with pytest.raises(IntegrityError), transaction.atomic():
        AuditEvent.objects.filter(pk=first.pk).delete()


def test_deactivation_and_last_owner_protection(world):
    """Protect the final owner and immediately remove scope from inactive memberships."""
    a = world["a"]
    client, _, _ = sign_in(a["user"], world["password"])
    assert (
        post(
            client, root(a["org"]) + f"members/{a['member'].pk}/", {"active": False}, method="patch"
        ).status_code
        == 400
    )
    a["member"].active = False
    a["member"].save()
    assert client.get(root(a["org"]) + "sites/").status_code == 404


def test_site_admin_cannot_escalate_or_inspect_other_site_roles(world):
    """Site administrators manage only nonprivileged grants and cannot enumerate nested scopes."""
    a = world["a"]
    user = CustomUser.objects.create_user(
        "manager@example.invalid", world["password"], verified_at=timezone.now()
    )
    member = Membership.objects.create(organisation=a["org"], user=user)
    RoleAssignment.objects.create(
        organisation=a["org"], membership=member, role=Role.SITE_ADMIN, site=a["sites"][0]
    )
    subject = CustomUser.objects.create_user(
        "subject@example.invalid", world["password"], verified_at=timezone.now()
    )
    subject_member = Membership.objects.create(organisation=a["org"], user=subject)
    for site in a["sites"]:
        RoleAssignment.objects.create(
            organisation=a["org"], membership=subject_member, role=Role.OPERATOR, site=site
        )
    client, _, _ = sign_in(user, world["password"])
    base = root(a["org"])
    visible = client.get(base + "members/").json()["results"]
    nested = next(item for item in visible if item["id"] == str(subject_member.pk))
    assert len(nested["roles"]) == 1
    assert nested["roles"][0]["site"] == str(a["sites"][0].pk)
    for role in [Role.OWNER, Role.SITE_ADMIN, Role.QA]:
        result = post(
            client,
            base + "roles/",
            {
                "membership_id": str(subject_member.pk),
                "role": role,
                "site_id": str(a["sites"][0].pk) if role != Role.OWNER else None,
            },
        )
        assert result.status_code == 403
    assert (
        post(
            client,
            base + "roles/",
            {
                "membership_id": str(subject_member.pk),
                "role": Role.AUDITOR,
                "site_id": str(a["sites"][1].pk),
            },
        ).status_code
        == 403
    )
    result = post(
        client,
        base + "roles/",
        {
            "membership_id": str(subject_member.pk),
            "role": Role.AUDITOR,
            "site_id": str(a["sites"][0].pk),
        },
    )
    assert result.status_code == 201
    assert post(client, base + f"roles/{result.json()['id']}/revoke/").status_code == 204


def test_owner_site_configuration_and_invitation_mail(
    world, django_capture_on_commit_callbacks, mailoutbox
):
    """Create planned-only sites and deliver expiring proof solely to the local mail backend."""
    a = world["a"]
    client, _, _ = sign_in(a["user"], world["password"])
    base = root(a["org"])
    site = post(
        client, base + "sites/", {"name": "New synthetic site", "timezone": "Europe/Copenhagen"}
    )
    assert site.status_code == 201
    assert site.json()["service_state"] == "planned"
    with django_capture_on_commit_callbacks(execute=True):
        response = post(
            client,
            base + "invitations/",
            {"email": "invited@example.invalid", "role": "operator", "site_id": site.json()["id"]},
        )
    assert response.status_code == 201
    assert len(mailoutbox) == 1
    assert "/accept#token=" in mailoutbox[0].body
    assert "token_hash" not in response.json()
    invitation = Invitation.objects.get(pk=response.json()["id"])
    token = mailoutbox[0].body.split("#token=")[1]
    assert invitation.token_hash == token_digest(token)
    assert post(client, base + f"invitations/{invitation.pk}/revoke/").status_code == 200
    assert (
        post(
            APIClient(enforce_csrf_checks=True),
            "/api/v1/auth/invitations/accept/",
            {"token": token, "password": world["password"]},
        ).status_code
        == 400
    )


def test_reset_worker_does_not_enumerate_or_log_bearer_tokens(world, mailoutbox):
    """The actual task sends only known verified accounts and persists a digest, never the token."""
    from sii.accounts.tasks import send_password_reset

    send_password_reset("absent@example.invalid")
    assert not mailoutbox
    send_password_reset(world["a"]["user"].email)
    assert len(mailoutbox) == 1
    token = mailoutbox[0].body.split("#token=")[1]
    assert PasswordReset.objects.filter(token_hash=token_digest(token)).exists()
    assert not AuditEvent.objects.filter(subject__contains=token).exists()


def test_unicode_totp_and_expired_pre_auth_fail_closed(world):
    """Non-ASCII digits must produce a bounded denial, and an expired challenge cannot enroll."""
    client, _, _ = sign_in(world["a"]["user"], world["password"], mfa=False)
    assert post(client, "/api/v1/auth/mfa/enroll/").status_code == 200
    assert post(client, "/api/v1/auth/mfa/verify/", {"code": "١٢٣٤٥٦"}).status_code == 403
    session = client.session
    session["pending_at"] = time.time() - 601
    session.save()
    assert post(client, "/api/v1/auth/mfa/enroll/").status_code == 403


def test_fresh_step_up_and_privilege_elevation_recheck(world, monkeypatch):
    """A new unused TOTP authorizes edits; a newly privileged password-only session is denied."""
    a = world["a"]
    client, secret, _ = sign_in(a["user"], world["password"])
    a["user"].refresh_from_db()
    future = (a["user"].mfa_last_counter + 1) * 30
    monkeypatch.setattr("sii.accounts.security.time.time", lambda: future)
    assert (
        post(
            client,
            "/api/v1/auth/step-up/",
            {"password": world["password"], "code": pyotp.TOTP(secret).at(future)},
        ).status_code
        == 200
    )
    user = CustomUser.objects.create_user(
        "promoted@example.invalid", world["password"], verified_at=timezone.now()
    )
    member = Membership.objects.create(organisation=a["org"], user=user)
    RoleAssignment.objects.create(
        organisation=a["org"], membership=member, role=Role.OPERATOR, site=a["sites"][0]
    )
    low, _, _ = sign_in(user, world["password"])
    assert low.get("/api/v1/me/").status_code == 200
    assert (
        post(
            client,
            root(a["org"]) + "roles/",
            {"membership_id": str(member.pk), "role": "qa", "site_id": str(a["sites"][0].pk)},
        ).status_code
        == 201
    )
    assert low.get("/api/v1/me/").status_code == 403
