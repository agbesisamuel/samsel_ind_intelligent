"""Protect commercial scope, concurrent quotas, continued ingestion and support privacy."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.utils import timezone
from test_assets import endpoint, inventory  # noqa: F401
from test_identity_tenancy import post, root, sign_in
from test_telemetry import event, qualified  # noqa: F401

from sii.accounts.models import CustomUser
from sii.assets.models import Sensor
from sii.billing.models import InvoiceDraft, Plan, Subscription
from sii.billing.services import status, usage
from sii.billing.views import csv_cell
from sii.incidents.services import observe
from sii.support.models import SupportTicket, TicketEvent
from sii.telemetry.services import ingest
from sii.tenants.models import Membership, Organisation, RoleAssignment, Site


def allocation(fixture, sites=2, sensors=1, per_site=1):
    """Select a deliberately constrained immutable fixture plan, independent of demo defaults."""
    plan = Plan.objects.create(
        code="constrained-fixture",
        name="SYNTHETIC quota case",
        max_sites=sites,
        max_sensors=sensors,
        max_sensors_per_site=per_site,
        features=[],
    )
    Subscription.objects.filter(organisation=fixture["a"]["organisation"]).update(plan=plan)
    return plan


def sensor_data(fixture, suffix):
    """Construct an exact-site planned probe; this creates no qualification/live monitoring."""
    a = fixture["a"]
    return {
        "organisation": a["organisation"],
        "site": a["site"],
        "gateway": a["gateway"],
        "zone": a["zone"],
        "external_id": "SYNTHETIC-" + suffix,
        "name": "SYNTHETIC quota probe",
        "expected_interval_sec": 60,
    }


@pytest.mark.django_db
def test_quota_api_raw_writes_and_catalog_immutability(inventory):  # noqa: F811
    """Neither API nor direct/bulk writes can exceed site/probe limits or rewrite a shared plan."""
    plan = allocation(inventory)
    org = inventory["a"]["organisation"]
    client = inventory["client"]
    assert post(client, root(org) + "sites/", {"name": "Over capacity"}).status_code == 400
    with pytest.raises(IntegrityError), transaction.atomic():
        Site.objects.create(organisation=org, name="Raw capacity bypass")
    payload = {
        key: str(value.pk) if hasattr(value, "pk") else value
        for key, value in sensor_data(inventory, "api").items()
        if key not in {"organisation", "site"}
    }
    rejected = post(client, endpoint(inventory["a"]) + "sensors/", payload)
    assert rejected.status_code == 400
    with pytest.raises(IntegrityError), transaction.atomic():
        Sensor.objects.bulk_create([Sensor(**sensor_data(inventory, "raw"))])
    with pytest.raises(IntegrityError), transaction.atomic():
        Plan.objects.filter(pk=plan.pk).update(max_sites=100000)
    # An existing asset's non-capacity metadata is still editable while over quota.
    sensor = inventory["a"]["sensor"]
    sensor.name = "SYNTHETIC retained existing probe"
    sensor.save(update_fields=["name"])
    # The same API payload succeeds after an explicit larger fixture allocation;
    # the earlier denial is capacity enforcement, not an invalid probe contract.
    expanded = Plan.objects.create(
        code="expanded-fixture",
        name="SYNTHETIC larger allocation",
        max_sites=10,
        max_sensors=10,
        max_sensors_per_site=10,
        features=[],
    )
    Subscription.objects.filter(organisation=org).update(plan=expanded)
    assert post(client, endpoint(inventory["a"]) + "sensors/", payload).status_code == 201


@pytest.mark.django_db
def test_default_trial_and_unarchive_are_enforced(inventory):  # noqa: F811
    """Provision finite trials and prevent capacity bypass through archive/reactivation."""
    customer = Organisation.objects.create(name="SYNTHETIC trial provisioning")
    subscription = Subscription.objects.get(organisation=customer)
    assert subscription.plan_id == "local-trial-v1" and subscription.ends_at
    for n in range(2):
        Site.objects.create(organisation=customer, name=f"SYNTHETIC trial site {n}")
    with pytest.raises(IntegrityError), transaction.atomic():
        Site.objects.create(organisation=customer, name="Third trial site")
    allocation(inventory)
    org, client = inventory["a"]["organisation"], inventory["client"]
    site = inventory["a"]["site"]
    assert (
        post(
            client, root(org) + f"sites/{site.pk}/", {"archived": True}, method="patch"
        ).status_code
        == 200
    )
    assert (
        post(client, root(org) + "sites/", {"name": "Replacement planned site"}).status_code == 201
    )
    assert (
        post(
            client, root(org) + f"sites/{site.pk}/", {"archived": False}, method="patch"
        ).status_code
        == 400
    )


@pytest.mark.django_db
def test_expired_commercial_state_never_disables_ingestion(qualified):  # noqa: F811
    """Block expansion after expiry while retaining existing-device observations and response."""
    org = qualified["a"]["organisation"]
    Subscription.objects.filter(organisation=org).update(state="ended")
    result = ingest(qualified["credential"], event(qualified), "https")
    assert result["status"] == "accepted"
    current = status(Subscription.objects.select_related("plan").get(organisation=org))
    assert not current["expansion_allowed"] and current["monitoring_suspended"] is False
    with pytest.raises(IntegrityError), transaction.atomic():
        Sensor.objects.bulk_create([Sensor(**sensor_data(qualified, "after-end"))])


@pytest.mark.django_db
def test_finance_scope_idempotency_and_manual_csv(inventory):  # noqa: F811
    """Require platform authority for drafts and exact owner scope for exports."""
    world = inventory["world"]
    admin = CustomUser.objects.create_superuser(
        "finance@example.invalid", world["password"], verified_at=timezone.now()
    )
    platform, _, _ = sign_in(admin, world["password"])
    org, owner = inventory["a"]["organisation"], inventory["client"]
    base = root(org)
    assert platform.get(base + "subscription/").status_code == 200
    assert platform.get(base + "sites/").status_code == 404
    data = {
        "reference": "SYNTHETIC-001",
        "period_start": "2026-10-01",
        "period_end": "2026-10-20",
        "currency": "DKK",
        "net_amount": "100.00",
        "tax_amount": "25.00",
    }
    assert post(owner, base + "invoices/", data).status_code == 403
    created = post(platform, base + "invoices/", data)
    assert created.status_code == 201
    assert post(platform, base + "invoices/", data).data["id"] == created.data["id"]
    assert post(platform, base + "invoices/", {**data, "net_amount": "200.00"}).status_code == 400
    assert post(platform, base + "invoices/", {**data, "paid": True}).status_code == 400
    export = owner.get(base + f"invoices/{created.data['id']}/export/")
    assert export.status_code == 200 and b"SYNTHETIC_FINANCE_DRAFT" in export.content
    assert b"125.00" in export.content and export["Cache-Control"] == "no-store"
    foreign, _, _ = sign_in(world["b"]["user"], world["password"])
    assert foreign.get(base + f"invoices/{created.data['id']}/export/").status_code == 404
    with pytest.raises(IntegrityError), transaction.atomic():
        InvoiceDraft.objects.filter(pk=created.data["id"]).update(net_amount=0)
    assert csv_cell("  =FORMULA() ").startswith("'")
    terms = {
        "plan": "local-pilot-v1",
        "state": "pilot",
        "ends_at": (timezone.now() + timedelta(days=1)).isoformat(),
        "reason": "SYNTHETIC reviewed local configuration",
    }
    assert post(owner, base + "subscription/", terms).status_code == 403
    changed = post(platform, base + "subscription/", terms)
    assert changed.status_code == 200 and "term_ends_within_7_days" in changed.data["warnings"]
    assert changed.data["live_collections_enabled"] is False
    history = owner.get(base + "subscription/history/")
    assert history.status_code == 200 and history.data["results"][0]["reason"] == terms["reason"]
    assert foreign.get(base + "subscription/history/").status_code == 404
    assert (
        post(
            platform, base + "subscription/", {**terms, "ends_at": "2026-11-20T12:00:00"}
        ).status_code
        == 400
    )


@pytest.mark.django_db
def test_expansion_expiry_uses_wall_time_inside_long_transaction(inventory):  # noqa: F811
    """A transaction opened before expiry cannot reserve new capacity after the deadline."""
    org = inventory["a"]["organisation"]
    allocation(inventory, sites=100, sensors=100, per_site=100)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE billing_subscription SET ends_at=clock_timestamp()+interval '100 milliseconds' "
            "WHERE organisation_id=%s",
            [org.pk],
        )
        cursor.execute("SELECT pg_sleep(0.15)")
    with pytest.raises(IntegrityError), transaction.atomic():
        Sensor.objects.bulk_create([Sensor(**sensor_data(inventory, "expired-wall-clock"))])


@pytest.mark.django_db
def test_support_history_archive_and_platform_boundaries(inventory):  # noqa: F811
    """Customer support remains scoped/immutable and resolving it never closes a safety incident."""
    a, client = inventory["a"], inventory["client"]
    base = endpoint(a)
    incident = observe(a["gateway"], a["sensor"], "too_warm", timezone.now(), uuid.uuid4(), {})
    request = {
        "request_id": str(uuid.uuid4()),
        "subject": "SYNTHETIC help",
        "body": "SYNTHETIC local training question",
    }
    ticket = post(client, base + "support-tickets/", request)
    assert ticket.status_code == 201
    assert post(client, base + "support-tickets/", request).data["id"] == ticket.data["id"]
    assert (
        post(
            client, base + "support-tickets/", {**request, "body": "Changed original content"}
        ).status_code
        == 400
    )
    url = base + f"support-tickets/{ticket.data['id']}/events/"
    note = {"revision": 0, "message": "SYNTHETIC training answer", "status": "resolved"}
    assert post(client, url, note).status_code == 201
    assert post(client, url, note).status_code == 400
    incident.refresh_from_db()
    assert incident.status == "open"
    with pytest.raises(IntegrityError), transaction.atomic():
        SupportTicket.objects.filter(pk=ticket.data["id"]).update(body="Rewritten")
    with pytest.raises(IntegrityError), transaction.atomic():
        TicketEvent.objects.filter(ticket_id=ticket.data["id"]).update(message="Rewritten")
    assert client.get(base + "artifact-archive/").status_code == 200
    status = client.get(base + "operational-status/").data
    assert status["production_eligible"] is False and "unresolved_incidents" in status["blockers"]
    for resource in ["artifact-archive/", "support-tickets/", "operational-status/"]:
        assert client.get(endpoint(inventory["b"]) + resource).status_code == 404
    admin = CustomUser.objects.create_superuser(
        "support-platform@example.invalid",
        inventory["world"]["password"],
        verified_at=timezone.now(),
    )
    platform, _, _ = sign_in(admin, inventory["world"]["password"])
    assert platform.get(root(a["organisation"]) + "subscription/").status_code == 200
    assert platform.get(base + "support-tickets/").status_code == 404


@pytest.mark.django_db
def test_operator_ticket_privacy_and_commercial_denial(inventory):  # noqa: F811
    """A site-only operator cannot read other requesters, tenant billing or report archives."""
    a, owner = inventory["a"], inventory["client"]
    base = endpoint(a)
    original = post(
        owner,
        base + "support-tickets/",
        {
            "request_id": str(uuid.uuid4()),
            "subject": "SYNTHETIC owner request",
            "body": "SYNTHETIC private owner training note",
        },
    )
    password = inventory["world"]["password"]
    user = CustomUser.objects.create_user(
        "second-operator@example.invalid", password, verified_at=timezone.now()
    )
    membership = Membership.objects.create(organisation=a["organisation"], user=user)
    RoleAssignment.objects.create(
        organisation=a["organisation"], membership=membership, site=a["site"], role="operator"
    )
    client, _, _ = sign_in(user, password)
    assert client.get(base + "support-tickets/").data["count"] == 0
    assert client.get(base + f"support-tickets/{original.data['id']}/events/").status_code == 404
    assert client.get(root(a["organisation"]) + "subscription/").status_code == 403
    assert client.get(base + "artifact-archive/").status_code == 403
    own = post(
        client,
        base + "support-tickets/",
        {
            "request_id": str(uuid.uuid4()),
            "subject": "SYNTHETIC operator help",
            "body": "SYNTHETIC own training question",
        },
    )
    assert own.status_code == 201 and client.get(base + "support-tickets/").data["count"] == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_raw_sensor_inserts_cannot_overrun_quota(inventory):  # noqa: F811
    """Accept exactly one of two independent SQL transactions competing for one probe slot."""
    org = inventory["a"]["organisation"]
    before = usage(org.pk)["sensors"]
    allocation(inventory, sites=100, sensors=before + 1, per_site=100)
    # Prove the exact insertion is otherwise valid, without consuming the race slot.
    with transaction.atomic():
        Sensor.objects.bulk_create([Sensor(**sensor_data(inventory, "preflight"))])
        transaction.set_rollback(True)
    barrier = Barrier(2)

    def insert(suffix):
        """Exercise the database-only race guard through a separate connection and bulk write."""
        close_old_connections()
        try:
            with transaction.atomic():
                barrier.wait(timeout=15)
                Sensor.objects.bulk_create([Sensor(**sensor_data(inventory, suffix))])
            return True
        except IntegrityError:
            return False
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(insert, ["race-a", "race-b"]))
    assert sum(results) == 1
    assert usage(org.pk)["sensors"] == before + 1
