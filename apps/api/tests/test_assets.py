"""Sprint 03 T-07/T-20 and nested site-isolation tests using real MFA sessions/PostgreSQL."""

from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from test_identity_tenancy import post, sign_in

from sii.assets.models import (
    Building,
    CalibrationRecord,
    CommissioningAcceptance,
    Gateway,
    Sensor,
    Zone,
)
from sii.assets.services import sensor_qualification
from sii.tenants.models import Role, RoleAssignment

pytestmark = pytest.mark.django_db


@pytest.fixture
def inventory(world):
    """Build disjoint inventory in both tenants and a second A site for same-tenant scope tests."""
    result = {"world": world}
    for key, org, site in [
        ("a", world["a"]["org"], world["a"]["sites"][0]),
        ("a2", world["a"]["org"], world["a"]["sites"][1]),
        ("b", world["b"]["org"], world["b"]["sites"][0]),
    ]:
        scope = {"organisation": org, "site": site}
        building = Building.objects.create(**scope, name="Synthetic building")
        zone = Zone.objects.create(
            **scope, building=building, name="Synthetic room", zone_type="cold_room"
        )
        gateway = Gateway.objects.create(
            **scope, external_id=key + "-gateway", name="Simulator gateway"
        )
        sensor = Sensor.objects.create(
            **scope,
            zone=zone,
            gateway=gateway,
            external_id=key + "-sensor",
            name="Synthetic probe",
            expected_interval_sec=60,
        )
        result[key] = {
            **scope,
            "building": building,
            "zone": zone,
            "gateway": gateway,
            "sensor": sensor,
        }
    a = world["a"]
    RoleAssignment.objects.create(
        organisation=a["org"], membership=a["member"], role=Role.QA, site=a["sites"][0]
    )
    result["client"], _, _ = sign_in(a["user"], world["password"])
    return result


def endpoint(scope):
    """Build exact organisation/site nesting, never infer authority from submitted IDs."""
    return f"/api/v1/organisations/{scope['organisation'].pk}/sites/{scope['site'].pk}/"


@pytest.mark.parametrize(
    "resource",
    [
        "buildings",
        "zones",
        "gateways",
        "sensors",
        "calibrations",
        "sensor-commissionings",
        "commissioning",
        "commissioning-tests",
        "acceptances",
    ],
)
def test_inventory_foreign_collection_matrix(inventory, resource):
    """Every inventory/evidence collection rejects foreign scope before returning counts."""
    assert inventory["client"].get(endpoint(inventory["b"]) + resource + "/").status_code == 404


def test_nested_hierarchy_and_mass_assignment_rejected(inventory):
    """Reject another site's related IDs and attempts to supply tenant/state/actor fields."""
    c, a, a2, b = inventory["client"], inventory["a"], inventory["a2"], inventory["b"]
    base = endpoint(a)
    for foreign in [a2, b]:
        assert c.get(base + f"sensors/{foreign['sensor'].pk}/").status_code == 404
        assert (
            post(
                c,
                base + "zones/",
                {
                    "building": str(foreign["building"].pk),
                    "name": "Invalid",
                    "zone_type": "cold_room",
                },
            ).status_code
            == 404
        )
        assert (
            post(
                c,
                base + "sensors/",
                {
                    "zone": str(a["zone"].pk),
                    "gateway": str(foreign["gateway"].pk),
                    "name": "Invalid",
                    "external_id": "bad",
                    "expected_interval_sec": 60,
                },
            ).status_code
            == 404
        )
    for field, value in [
        ("organisation", str(b["organisation"].pk)),
        ("state", "active"),
        ("last_heartbeat_at", timezone.now().isoformat()),
    ]:
        assert (
            post(
                c, base + "gateways/", {"name": "bad", "external_id": "bad", field: value}
            ).status_code
            == 400
        )
    assert (
        post(
            c,
            base + f"sensors/{a['sensor'].pk}/",
            {"gateway": str(a2["gateway"].pk)},
            method="patch",
        ).status_code
        == 400
    )


def test_t07_calibration_unknown_expired_and_synthetic_valid(inventory):
    """A current reference is marked synthetic; absent or expired metadata never implies safety."""
    c, a = inventory["client"], inventory["a"]
    now = timezone.now()
    assert sensor_qualification(a["sensor"])["calibration_status"] == "unknown"
    response = post(
        c,
        endpoint(a) + "calibrations/",
        {
            "sensor": str(a["sensor"].pk),
            "reference": "SYNTHETIC reference",
            "checked_at": (now - timedelta(days=1)).isoformat(),
            "due_at": (now + timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 201, response.content
    assert response.json()["synthetic"] is True
    assert sensor_qualification(a["sensor"])["calibration_status"] == "synthetic_valid"
    assert (
        sensor_qualification(a["sensor"], now + timedelta(days=2))["calibration_status"]
        == "expired"
    )
    assert (
        post(
            c,
            endpoint(a) + "calibrations/",
            {
                "sensor": str(a["sensor"].pk),
                "reference": "bad",
                "checked_at": (now + timedelta(days=1)).isoformat(),
                "due_at": (now + timedelta(days=2)).isoformat(),
            },
        ).status_code
        == 400
    )
    for kind in ["patch", "delete"]:
        assert (
            post(
                c,
                endpoint(a) + f"calibrations/{response.json()['id']}/",
                {"reference": "rewrite"},
                method=kind,
            ).status_code
            == 405
        )


def test_owner_is_not_implicitly_qa(inventory):
    """Owners cannot approve calibration or commissioning without an explicit QA grant."""
    a, c = inventory["a"], inventory["client"]
    RoleAssignment.objects.filter(
        membership=inventory["world"]["a"]["member"], role=Role.QA
    ).delete()
    assert post(c, endpoint(a) + "calibrations/", {}).status_code == 403


def test_t20_lifecycle_and_activation_are_fail_closed(inventory):
    """Local evidence cannot activate monitoring, and retirement cannot be undone through CRUD."""
    c, a = inventory["client"], inventory["a"]
    for resource in ["sensors", "gateways"]:
        obj = a["sensor" if resource == "sensors" else "gateway"]
        route = endpoint(a) + resource + f"/{obj.pk}/transition/"
        assert post(c, route, {"target": "commissioning"}).status_code == 200
        assert post(c, route, {"target": "active"}).status_code == 400
        assert post(c, route, {"target": "retired"}).status_code == 200
        assert post(c, route, {"target": "commissioning"}).status_code == 400
    response = post(c, endpoint(a) + "activation/")
    assert response.status_code == 409
    assert "synthetic_environment_cannot_activate_live_monitoring" in response.json()["blockers"]
    a["site"].refresh_from_db()
    assert a["site"].service_state == "planned"


def test_qa_acceptance_requires_complete_current_evidence(inventory):
    """QA accepts a complete synthetic snapshot only; it never becomes a live customer approval."""
    c, a = inventory["client"], inventory["a"]
    base = endpoint(a)
    pack = post(
        c,
        base + "commissioning/",
        {
            "responsible_person": "Synthetic QA",
            "read_only_scope": True,
            "customer_approval_reference": "SYNTHETIC acceptance",
            "contingency_reference": "SYNTHETIC contingency",
        },
    )
    assert pack.status_code == 201, pack.content
    pack_id = pack.json()["id"]
    assert post(c, base + f"commissioning/{pack_id}/accept/").status_code == 400
    for key in ["sensor", "gateway"]:
        assert (
            post(
                c, base + key + f"s/{a[key].pk}/transition/", {"target": "commissioning"}
            ).status_code
            == 200
        )
    now = timezone.now()
    assert (
        post(
            c,
            base + "calibrations/",
            {
                "sensor": str(a["sensor"].pk),
                "reference": "SYNTHETIC",
                "checked_at": (now - timedelta(minutes=1)).isoformat(),
                "due_at": (now + timedelta(days=1)).isoformat(),
            },
        ).status_code
        == 201
    )
    assert (
        post(
            c,
            base + "sensor-commissionings/",
            {
                "sensor": str(a["sensor"].pk),
                "technician_reference": "Synthetic technician",
                "placement_reference": "Synthetic placement",
                "read_only_scope": True,
            },
        ).status_code
        == 201
    )
    for kind in ["sensor_feed", "breach", "no_data", "routing"]:
        assert (
            post(
                c,
                base + "commissioning-tests/",
                {
                    "commissioning": pack_id,
                    "kind": kind,
                    "passed": True,
                    "evidence_reference": "SYNTHETIC manual drill",
                },
            ).status_code
            == 201
        )
    accepted = post(c, base + f"commissioning/{pack_id}/accept/")
    assert accepted.status_code == 201, accepted.content
    assert accepted.json()["synthetic"] is True
    assert accepted.json()["current"] is True
    # Acceptance preserves its original configuration snapshot as later edits invalidate currency.
    saved = accepted.json()["evidence_snapshot"]
    assert saved["sensors"][str(a["sensor"].pk)]["expected_interval_sec"] == 60
    assert (
        post(
            c, base + f"sensors/{a['sensor'].pk}/", {"expected_interval_sec": 120}, method="patch"
        ).status_code
        == 200
    )
    reviewed = c.get(base + f"acceptances/{accepted.json()['id']}/").json()
    assert reviewed["current"] is False
    assert reviewed["evidence_snapshot"] == saved
    assert post(c, base + "activation/").status_code == 409
    assert not CommissioningAcceptance.objects.filter(synthetic=False).exists()


def test_database_prevents_bulk_cross_site_and_evidence_rewrite(inventory):
    """PostgreSQL protects raw/bulk callers independently of serializer and model checks."""
    a, a2 = inventory["a"], inventory["a2"]
    with pytest.raises(IntegrityError), transaction.atomic():
        Sensor.objects.bulk_create(
            [
                Sensor(
                    organisation=a["organisation"],
                    site=a["site"],
                    zone=a["zone"],
                    gateway=a2["gateway"],
                    name="bad",
                    external_id="bad",
                    expected_interval_sec=60,
                )
            ]
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        Sensor.objects.filter(pk=a["sensor"].pk).update(site=a2["site"])
    with pytest.raises(IntegrityError), transaction.atomic():
        Gateway.objects.filter(pk=a["gateway"].pk).update(external_id="reassigned")
    record = CalibrationRecord.objects.create(
        organisation=a["organisation"],
        site=a["site"],
        sensor=a["sensor"],
        reference="SYNTHETIC",
        checked_at=timezone.now(),
        due_at=timezone.now() + timedelta(days=1),
        recorded_by=inventory["world"]["a"]["user"],
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        CalibrationRecord.objects.filter(pk=record.pk).update(reference="tamper")
    with pytest.raises(IntegrityError), transaction.atomic():
        CalibrationRecord.objects.filter(pk=record.pk).delete()
