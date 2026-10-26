"""Deterministic rule and incident evidence tests; all thresholds are fictional test inputs."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from test_assets import endpoint, inventory  # noqa: F401
from test_identity_tenancy import post
from test_monitoring import approve as approve_timing
from test_telemetry import event, qualified  # noqa: F401

from sii.incidents.models import Incident, IncidentEvent
from sii.monitoring.services import refresh_sensor
from sii.rules.engine import step
from sii.rules.models import RuleEvaluation, RuleSet, RuleVersion, SuppressionWindow
from sii.rules.services import (
    activate,
    approve,
    backtest,
    config,
    evaluate_health,
    evaluate_reading,
)
from sii.telemetry.models import Reading
from sii.telemetry.services import ingest
from sii.tenants.models import RoleAssignment

CONFIG = {
    "lower_bound": "0",
    "upper_bound": "10",
    "hysteresis": "1",
    "sustained_sec": 120,
    "recovery_sec": 120,
}


def test_config_matches_database_decimal_representation():
    """Programmatic integer inputs must not invalidate approvals after a DB round trip."""
    from types import SimpleNamespace

    fields = {**CONFIG, "sop_reference": "SYNTHETIC"}
    raw = SimpleNamespace(**{**fields, "lower_bound": 0, "upper_bound": 10, "hysteresis": 1})
    stored = SimpleNamespace(
        **{
            **fields,
            "lower_bound": Decimal("0.0000"),
            "upper_bound": Decimal("10.0000"),
            "hysteresis": Decimal("1.0000"),
        }
    )
    assert config(raw) == config(stored)


@pytest.mark.parametrize(
    "values, offsets, expected",
    [
        ([11, 11, 11], [0, 60, 120], ["breached"]),
        ([11, 10, 11, 10, 11], [0, 60, 120, 180, 240], []),
        ([11, 11, 11], [0, 60, 300], []),
        ([11, 11, 11, 9.5, 9.5, 9.5], [0, 60, 120, 180, 240, 300], ["breached"]),
        ([11, 11, 11, 9, 9, 9], [0, 60, 120, 180, 240, 300], ["breached", "recovered"]),
        ([-1, -1, -1], [0, 60, 120], ["breached"]),
    ],
)
def test_sustained_hysteresis_gap_machine(values, offsets, expected):
    """Require sustained consecutive evidence; debounce jitter and restart timing after gaps."""
    state, actions = {}, []
    origin = datetime(2026, 1, 1, tzinfo=UTC)
    for value, offset in zip(values, offsets, strict=True):
        state, changes, _ = step(
            CONFIG, state, origin + timedelta(seconds=offset), Decimal(str(value)), 60, 10
        )
        actions.extend(change["transition"] for change in changes)
    assert actions == expected
    # The supplied cursor is not modified when an older event arrives.
    result, changes, reason = step(CONFIG, state, origin, Decimal("0"), 60, 10)
    assert reason == "late" and result == state and changes == []


@pytest.fixture
def armed(qualified):  # noqa: F811
    """Build explicit synthetic QA-tested approval and an immediate effective boundary."""
    approve_timing(qualified, grace=10)
    a = qualified["a"]
    scope = {"organisation": a["organisation"], "site": a["site"]}
    family = RuleSet.objects.create(**scope, zone=a["zone"], name="Fictional temperature policy")
    version = RuleVersion.objects.create(
        **scope,
        ruleset=family,
        version=1,
        **CONFIG,
        sop_reference="SYNTHETIC test SOP; no food recommendation",
        created_by=qualified["world"]["a"]["user"],
    )
    for index in range(3):
        ingest(
            qualified["credential"],
            event(
                qualified,
                sequence=index + 1,
                observed_at=(timezone.now() - timedelta(seconds=300 - index * 60)).isoformat(),
                value="11",
            ),
            "https",
        )
    version.refresh_from_db()
    user = qualified["world"]["a"]["user"]
    preview = backtest(version, user, timezone.now() - timedelta(hours=1), timezone.now())
    approval = approve(version, preview.pk, user)
    activation = activate(approval, user)
    return {
        **qualified,
        "version": version,
        "preview": preview,
        "approval": approval,
        "activation": activation,
        "origin": activation.effective_at + timedelta(seconds=1),
    }


def feed(fixture, index, value, observed=None):
    """Advance an injected synthetic clock so source and receipt times match a normal live trace."""
    now = fixture["origin"] + timedelta(seconds=index * 60)
    with patch("django.utils.timezone.now", return_value=now):
        payload = event(
            fixture,
            sequence=100 + index,
            value=str(value),
            observed_at=(observed or now).isoformat(),
        )
        receipt = ingest(fixture["credential"], payload, "https")
        assert receipt["status"] == "accepted"
        reading = Reading.objects.get(pk=receipt["reading_id"])
        evaluate_reading(reading)
        return reading


@pytest.mark.django_db
def test_episode_retry_recovery_and_late_evidence(armed):
    """One sustained breach opens once; recovery records evidence without closing human work."""
    samples = [feed(armed, index, value) for index, value in enumerate([11, 11, 11, 9, 9, 9])]
    assert Incident.objects.count() == 1
    incident = Incident.objects.get()
    assert incident.kind == "too_warm" and incident.status == "open"
    assert incident.recovered_at is not None
    assert list(incident.events.order_by("occurred_at").values_list("kind", flat=True)) == [
        "incident.opened.v1",
        "incident.recovered.v1",
    ]
    for reading in samples:
        evaluate_reading(reading)
    assert RuleEvaluation.objects.count() == 6 and IncidentEvent.objects.count() == 2
    feed(armed, 6, 20, observed=armed["origin"] + timedelta(seconds=270))
    assert RuleEvaluation.objects.order_by("-evaluated_at").first().result["reason"] == "late"
    assert IncidentEvent.objects.count() == 2


@pytest.mark.django_db
def test_suppression_preserves_visible_incident(armed):
    """Maintenance records scope/reason/expiry without hiding a sustained breach or its history."""
    scope = {"organisation": armed["a"]["organisation"], "site": armed["a"]["site"]}
    window = SuppressionWindow.objects.create(
        **scope,
        sensor=armed["a"]["sensor"],
        start=armed["origin"] - timedelta(seconds=1),
        end=armed["origin"] + timedelta(hours=1),
        reason="SYNTHETIC maintenance drill",
        created_by=armed["world"]["a"]["user"],
    )
    for index in range(3):
        feed(armed, index, 11)
    assert Incident.objects.get().status == "open"
    assert IncidentEvent.objects.get().evidence["suppression"] == str(window.pk)


@pytest.mark.django_db
def test_unapproved_or_stale_policy_never_governs(armed):
    """Changing approved cadence invalidates evaluation; owners cannot substitute QA approval."""
    sensor = armed["a"]["sensor"]
    sensor.expected_interval_sec = 90
    sensor.save()
    feed(armed, 0, 11)
    assert RuleEvaluation.objects.get().result["reason"] == "approval_stale"
    assert Incident.objects.count() == 0
    RoleAssignment.objects.filter(membership=armed["world"]["a"]["member"], role="qa").delete()
    url = endpoint(armed["a"]) + f"rule-versions/{armed['version'].pk}/approve/"
    assert post(armed["client"], url, {"backtest": str(armed["preview"].pk)}).status_code == 403


@pytest.mark.django_db
def test_no_data_and_gateway_failures_are_independent(qualified):  # noqa: F811
    """Approved grace creates separate missing-data/offline evidence without threshold input."""
    policy = approve_timing(qualified, grace=10, gateway=120)
    at = policy.approved_at + timedelta(seconds=121)
    projection = refresh_sensor(qualified["a"]["sensor"].pk, at)
    evaluate_health(projection)
    evaluate_health(projection)
    assert set(Incident.objects.values_list("kind", flat=True)) == {
        "sensor_no_data",
        "gateway_offline",
    }
    assert IncidentEvent.objects.count() == 2


@pytest.mark.django_db
def test_rule_and_incident_scope_immutability(armed):
    """Foreign IDs fail closed; SQL cannot edit approved versions or incident timelines."""
    client, foreign = armed["client"], endpoint(armed["b"])
    for route in ["rule-families/", "rule-versions/", "maintenance/", "incidents/"]:
        assert client.get(foreign + route).status_code == 404
    for index in range(3):
        feed(armed, index, 11)
    incident = Incident.objects.get()
    assert client.get(foreign + f"incidents/{incident.pk}/events/").status_code == 404
    with pytest.raises(IntegrityError), transaction.atomic():
        RuleVersion.objects.filter(pk=armed["version"].pk).update(upper_bound=100)
    with pytest.raises(IntegrityError), transaction.atomic():
        IncidentEvent.objects.update(kind="incident.resolved.v1")
    assert (
        post(
            client, endpoint(armed["a"]) + f"rule-versions/{armed['version'].pk}/activate/", {}
        ).status_code
        == 400
    )


@pytest.mark.django_db
def test_api_preview_approval_supersession_and_delayed_boundary(armed):
    """Only reviewed versions activate; delayed old-version data cannot restart live evaluation."""
    client, base = armed["client"], endpoint(armed["a"])
    response = post(
        client,
        base + "rule-versions/",
        {
            **CONFIG,
            "ruleset": str(armed["version"].ruleset_id),
            "sop_reference": "SYNTHETIC revised SOP",
        },
    )
    assert response.status_code == 201, response.data
    version_id = response.data["id"]
    path = base + f"rule-versions/{version_id}/"
    assert post(client, path + "activate/", {}).status_code == 400
    preview = post(
        client,
        path + "backtests/",
        {
            "start": (timezone.now() - timedelta(hours=1)).isoformat(),
            "end": timezone.now().isoformat(),
        },
    )
    assert preview.status_code == 201, preview.data
    approval = post(client, path + "approve/", {"backtest": preview.data["id"]})
    assert approval.status_code == 201, approval.data
    boundary = armed["origin"] + timedelta(seconds=30)
    with patch("django.utils.timezone.now", return_value=boundary):
        response = post(client, path + "activate/", {})
        assert response.status_code == 201, response.data
    reading = feed(armed, 1, 11, observed=armed["origin"])
    result = RuleEvaluation.objects.get(reading=reading)
    assert result.version == armed["version"]
    assert result.result["reason"] == "superseded_late_evidence_only"
    stages = {
        item["version"]: item["stage"]
        for item in client.get(base + "rule-versions/").data["results"]
    }
    assert stages == {1: "superseded", 2: "active_synthetic"}
    assert not Incident.objects.exists()
    assert (
        post(
            client,
            base + "maintenance/",
            {
                "start": "2026-10-21T12:00:00",
                "end": "2026-10-21T13:00:00",
                "reason": "Ambiguous timestamp rejected",
            },
        ).status_code
        == 400
    )
