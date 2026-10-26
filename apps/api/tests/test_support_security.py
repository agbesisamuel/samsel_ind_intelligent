"""Protect support capabilities, customer isolation and independently verified audit chains."""

import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied
from test_assets import endpoint, inventory  # noqa: F401
from test_identity_tenancy import post, sign_in

from sii.accounts.models import CustomUser
from sii.audit.services import record
from sii.audit.verification import verify
from sii.support.models import SupportAccessLog, SupportSession
from sii.support.services import approve, diagnostics, revoke
from sii.tenants.models import RoleAssignment

pytestmark = pytest.mark.django_db


@pytest.fixture
def support(inventory):  # noqa: F811
    """Create independent verified platform staff with no customer assignments."""
    user = CustomUser.objects.create_user(
        "support@example.invalid",
        inventory["world"]["password"],
        is_staff=True,
        verified_at=timezone.now(),
    )
    client, _, _ = sign_in(user, inventory["world"]["password"])
    return inventory, user, client


def test_support_scope_mfa_expiry_revocation_and_audit(support):
    """A granted diagnostic handle cannot become customer browsing, export or indefinite access."""
    fixture, user, client = support
    owner, site = fixture["world"]["a"]["user"], fixture["a"]["site"]
    session = approve(owner, site, user, 30, "SYNTHETIC support investigation")
    assert client.get(endpoint(fixture["a"]) + "readings/").status_code == 404
    assert client.get(endpoint(fixture["a"]) + "reports/").status_code == 404
    url = f"/api/v1/support-sessions/{session.pk}/diagnostics/"
    assert client.get(url).status_code == 200
    assert SupportAccessLog.objects.filter(session=session).count() == 1
    with patch("sii.support.services.timezone.now", return_value=session.expires_at):
        with pytest.raises(NotFound):
            diagnostics(user, session.pk)
    revoke(owner, session)
    assert client.get(url).status_code == 404
    assert verify()


def test_staff_cannot_self_approve_or_mutate_support_scope(support):
    """Only an independent current customer owner can approve; database anchors remain fixed."""
    fixture, user, client = support
    site = fixture["a"]["site"]
    with pytest.raises(PermissionDenied):
        approve(user, site, user, 10, "SYNTHETIC attempt")
    assert (
        post(
            client,
            endpoint(fixture["a"]) + "support-sessions/",
            {"supporter": str(user.pk), "minutes": 30, "reason": "SYNTHETIC attempt"},
        ).status_code
        == 404
    )
    session = approve(fixture["world"]["a"]["user"], site, user, 10, "SYNTHETIC approved reason")
    with transaction.atomic(), pytest.raises(IntegrityError):
        SupportSession.objects.filter(pk=session.pk).update(
            expires_at=timezone.now() + timedelta(days=1)
        )
    with transaction.atomic(), pytest.raises(IntegrityError):
        SupportAccessLog.objects.create(
            organisation=site.organisation,
            site=fixture["a2"]["site"],
            session=session,
            action="diagnostics.read",
        )
    RoleAssignment.objects.filter(membership=fixture["world"]["a"]["member"], role="owner").delete()
    with pytest.raises(NotFound):
        diagnostics(user, session.pk)


def test_support_guessed_handles_and_wrong_staff_are_indistinguishable(support):
    """Deterministic identifier fuzz never leaks whether another capability exists."""
    fixture, user, client = support
    session = approve(
        fixture["world"]["a"]["user"], fixture["a"]["site"], user, 1, "SYNTHETIC limited access"
    )
    for identifier in [uuid.UUID(int=i) for i in range(12)]:
        assert client.get(f"/api/v1/support-sessions/{identifier}/diagnostics/").status_code == 404
    with pytest.raises(NotFound):
        diagnostics(fixture["world"]["b"]["user"], session.pk)
    session_state = client.session
    session_state["step_up_at"] = (timezone.now() - timedelta(minutes=6)).timestamp()
    session_state.save()
    assert client.get(f"/api/v1/support-sessions/{session.pk}/diagnostics/").status_code == 403


def test_audit_verifier_checks_heads_and_full_record_hash(world):
    """A changed hash input or incomplete head is detected independently of write-time triggers."""
    from sii.audit.models import AuditHead

    record("security.test", actor=world["a"]["user"], organisation=world["a"]["org"])
    assert verify()[0]["sequence"] == 1
    AuditHead.objects.filter(key=str(world["a"]["org"].pk)).update(event_hash="0" * 64)
    with pytest.raises(ValueError):
        verify()
