"""Protect consent, scope, bounded delivery retry and separate human acknowledgement."""

import re
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from django.core import mail
from django.db import IntegrityError, transaction
from django.utils import timezone
from test_assets import endpoint, inventory  # noqa: F401
from test_identity_tenancy import post

from sii.accounts.models import CustomUser
from sii.incidents.models import Incident, IncidentEvent
from sii.notifications import models, provider, services
from sii.rules.models import SuppressionWindow
from sii.tenants.models import Membership, RoleAssignment

pytestmark = pytest.mark.django_db


@pytest.fixture
def routed(inventory):  # noqa: F811
    """Request and personally confirm two disjoint site contacts through captured local proof."""
    result = dict(inventory)
    for key in ["a", "b"]:
        user = inventory["world"][key]["user"]
        contact = services.invite(inventory[key]["site"], user, user)
        proof = re.search(r"Proof: (\S+)", mail.outbox[-1].body).group(1)
        services.confirm(contact, proof, user)
        result[key] = {**inventory[key], "contact": models.AlertContact.objects.get(pk=contact.pk)}
    route = models.AlertRoute.objects.create(
        organisation=inventory["a"]["organisation"],
        site=inventory["a"]["site"],
        name="SYNTHETIC route",
        contact=result["a"]["contact"],
        kinds=["too_warm", "invalid_reading"],
        severity="warning",
        timezone="Europe/Copenhagen",
        shift_start=0,
        shift_end=1440,
        created_by=inventory["world"]["a"]["user"],
    )
    return {**result, "route": route}


def episode(fixture):
    """Create synthetic open evidence after route creation, matching the domain event contract."""
    scope = {"organisation": fixture["a"]["organisation"], "site": fixture["a"]["site"]}
    incident = Incident.objects.create(
        **scope,
        gateway=fixture["a"]["gateway"],
        sensor=fixture["a"]["sensor"],
        kind="too_warm",
        opened_at=timezone.now(),
    )
    return IncidentEvent.objects.create(
        **scope,
        incident=incident,
        kind="incident.opened.v1",
        occurred_at=timezone.now(),
        correlation_id=uuid.uuid4(),
    )


def test_consent_is_personal_single_use_and_expiring(inventory):  # noqa: F811
    """Possessing another recipient's token cannot opt them in; expiry and reuse fail closed."""
    user = inventory["world"]["a"]["user"]
    contact = services.invite(inventory["a"]["site"], user, user)
    proof = re.search(r"Proof: (\S+)", mail.outbox[-1].body).group(1)
    from rest_framework.exceptions import PermissionDenied

    with pytest.raises(PermissionDenied):
        services.confirm(contact, proof, inventory["world"]["b"]["user"])
    with patch("django.utils.timezone.now", return_value=contact.expires_at):
        with pytest.raises(PermissionDenied):
            services.confirm(contact, proof, user)
    services.confirm(contact, proof, user)
    with pytest.raises(PermissionDenied):
        services.confirm(contact, proof, user)
    assert mail.outbox[-1].subject.startswith("[TEST]")


def test_planning_and_worker_replay_never_duplicate_acceptance(routed):
    """Repeated planning/delivery produces one accepted message and leaves the incident open."""
    event = episode(routed)
    services.plan(event.pk)
    services.plan(event.pk)
    item = models.Notification.objects.get()
    before = len(mail.outbox)
    services.dispatch(item.pk)
    services.dispatch(item.pk)
    item.refresh_from_db()
    assert item.status == "accepted" and item.attempts == 1
    assert len(mail.outbox) == before + 1
    event.incident.refresh_from_db()
    assert event.incident.status == "open"
    assert models.EventPlan.objects.count() == 1
    assert item.envelope["site_id"] == str(event.site_id)


def test_provider_outage_bounded_retry_and_visible_issue(routed):
    """Five known failures produce dead-letter state, immutable attempts and a support signal."""
    item = services.enqueue(routed["route"], routed["a"]["contact"], "test", timezone.now())
    with patch("sii.notifications.provider.deliver", side_effect=provider.DeliveryFailure()):
        for _ in range(5):
            services.dispatch(item.pk, at=item.due_at)
            item.refresh_from_db()
    assert item.status == "dead" and item.history.count() == 5
    assert models.DeliveryIssue.objects.filter(notification=item, resolved_at=None).exists()
    services.dispatch(item.pk, at=item.due_at)
    assert item.history.count() == 5
    with pytest.raises(IntegrityError), transaction.atomic():
        item.history.update(outcome="accepted")


def test_lost_lease_never_blindly_resends(routed):
    """A crash between SMTP and commit becomes uncertain and does not duplicate a possible send."""
    item = services.enqueue(routed["route"], routed["a"]["contact"], "test", timezone.now())
    claimed = services.claim(item.pk, timezone.now())
    before = len(mail.outbox)
    with patch(
        "django.utils.timezone.now", return_value=claimed.lease_until + timedelta(seconds=1)
    ):
        services.tick()
    item.refresh_from_db()
    assert item.status == "uncertain" and len(mail.outbox) == before
    assert item.history.get().error_code == "worker_lease_lost"


def test_escalation_waits_for_human_ack_not_provider(routed):
    """Accepted initial delivery still escalates; human acknowledgement cancels a due escalation."""
    route = routed["route"]
    models.EscalationPolicy.objects.create(
        **services.scope(route), route=route, contact=route.contact, delay_sec=60
    )
    event = episode(routed)
    services.plan(event.pk)
    initial = models.Notification.objects.get(level="initial")
    escalation = models.Notification.objects.get(level="escalation")
    services.dispatch(initial.pk)
    assert services.claim(escalation.pk, initial.due_at) is None
    event.incident.status = "acknowledged"
    event.incident.save(update_fields=["status"])
    services.dispatch(escalation.pk, at=escalation.due_at)
    escalation.refresh_from_db()
    assert escalation.status == "ack_cancelled" and escalation.attempts == 0


def test_opt_out_and_maintenance_are_explicit(routed):
    """Cancel revoked contacts; retain maintenance-suppressed intent and incident evidence."""
    event = episode(routed)
    route = routed["route"]
    services.plan(event.pk)
    item = models.Notification.objects.get()
    SuppressionWindow.objects.create(
        **services.scope(route),
        sensor=event.incident.sensor,
        start=timezone.now() - timedelta(seconds=1),
        end=timezone.now() + timedelta(minutes=1),
        reason="SYNTHETIC maintenance",
        created_by=routed["world"]["a"]["user"],
    )
    services.dispatch(item.pk)
    item.refresh_from_db()
    assert item.status == "deferred_maintenance" and item.attempts == 0
    services.dispatch(item.pk, at=item.due_at)
    item.refresh_from_db()
    assert item.status == "accepted" and item.attempts == 1
    test = services.enqueue(route, route.contact, "test", timezone.now())
    route.contact.disabled = True
    route.contact.save(update_fields=["disabled"])
    services.dispatch(test.pk)
    test.refresh_from_db()
    assert test.status == "cancelled"


def test_shifts_respect_midnight_and_copenhagen_dst(routed):
    """Both repeated local 02:30 times are in a configured 22:00–06:00 night shift."""
    route = routed["route"]
    route.shift_start, route.shift_end = 22 * 60, 6 * 60
    assert services.in_shift(route, datetime(2026, 10, 25, 0, 30, tzinfo=UTC))
    assert services.in_shift(route, datetime(2026, 10, 25, 1, 30, tzinfo=UTC))
    assert not services.in_shift(route, datetime(2026, 10, 25, 12, tzinfo=UTC))


def test_scope_api_foreign_contacts_and_raw_reassignment(routed):
    """Exact-site API/DB guards prevent routing to another tenant or rewriting historical intent."""
    client, base = routed["client"], endpoint(routed["a"])
    for resource in ["alert-contacts/", "alert-routes/", "notifications/", "notification-health/"]:
        assert client.get(endpoint(routed["b"]) + resource).status_code == 404
    payload = {
        "name": "TEST",
        "contact": str(routed["b"]["contact"].pk),
        "kinds": ["too_warm"],
        "severity": "warning",
        "timezone": "Europe/Copenhagen",
        "shift_start": 0,
        "shift_end": 1440,
    }
    assert post(client, base + "alert-routes/", payload).status_code == 404
    payload["contact"] = str(routed["a"]["contact"].pk)
    response = post(client, base + "alert-routes/", payload)
    assert response.status_code == 201, response.data
    test = post(client, base + f"alert-routes/{response.data['id']}/test/", {})
    assert test.status_code == 201 and test.data["event"] is None
    assert not Incident.objects.exists()
    with pytest.raises(IntegrityError), transaction.atomic():
        models.Notification.objects.filter(pk=test.data["id"]).update(
            contact=routed["b"]["contact"]
        )


def test_contingency_is_once_and_cannot_recurse(routed):
    """Schedule fallback once through retries; its own failure cannot recurse."""
    old = routed["route"]
    route = models.AlertRoute.objects.create(
        **services.scope(old),
        name="TEST fallback",
        contact=old.contact,
        contingency=old.contact,
        kinds=old.kinds,
        severity=old.severity,
        timezone=old.timezone,
        shift_start=0,
        shift_end=1440,
        created_by=old.created_by,
    )
    item = services.enqueue(route, route.contact, "test", timezone.now())
    with patch("sii.notifications.provider.deliver", side_effect=provider.DeliveryFailure()):
        services.dispatch(item.pk)
        secondary = models.Notification.objects.get(level="contingency")
        services.dispatch(secondary.pk)
        item.refresh_from_db()
        services.dispatch(item.pk, at=item.due_at)
    assert models.Notification.objects.count() == 2


def test_unrouted_failure_is_visible_and_production_adapter_fails_closed(routed, monkeypatch):
    """Record unrouted issues and reject environment attempts to enable live email."""
    from django.core.exceptions import ImproperlyConfigured

    models.AlertRoute.objects.update(enabled=False)
    event = episode(routed)
    services.plan(event.pk)
    assert models.DeliveryIssue.objects.get().reason == "no_verified_route"
    monkeypatch.setenv("NOTIFICATION_PROVIDER", "live_smtp")
    with pytest.raises(ImproperlyConfigured):
        provider.deliver("synthetic@example.invalid", "test", "test", uuid.uuid4())


def test_multiple_contacts_and_revoked_grants_are_rechecked(routed):
    """Notify two verified contacts once each; revoked grants cancel pending work."""
    route = routed["route"]
    user = CustomUser.objects.create_user("second@example.invalid", verified_at=timezone.now())
    member = Membership.objects.create(organisation=route.organisation, user=user)
    grant = RoleAssignment.objects.create(
        organisation=route.organisation, site=route.site, membership=member, role="operator"
    )
    contact = services.invite(route.site, user, route.created_by)
    proof = re.search(r"Proof: (\S+)", mail.outbox[-1].body).group(1)
    services.confirm(contact, proof, user)
    second = models.AlertRoute.objects.create(
        **services.scope(route),
        name="Second contact",
        contact=contact,
        kinds=route.kinds,
        severity=route.severity,
        timezone=route.timezone,
        shift_start=0,
        shift_end=1440,
        created_by=route.created_by,
    )
    event = episode(routed)
    services.plan(event.pk)
    before = len(mail.outbox)
    for item in models.Notification.objects.all():
        services.dispatch(item.pk)
    assert len(mail.outbox) == before + 2
    assert {message.to[0] for message in mail.outbox[before:]} == {
        user.email,
        route.contact.user.email,
    }
    pending = services.enqueue(second, contact, "test", timezone.now())
    grant.delete()
    services.dispatch(pending.pk)
    pending.refresh_from_db()
    assert pending.status == "cancelled" and pending.attempts == 0
