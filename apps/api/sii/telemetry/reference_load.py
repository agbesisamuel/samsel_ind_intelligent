"""Guarded synthetic 20-site/800-probe workload through real TLS HTTP and independent workers.

This is a measured short baseline at the specified cadence, not a claimed 24-hour
soak or cloud availability result. Fixtures use explicit synthetic qualification,
timing and rule approvals. No live endpoint, customer ID or device URL is accepted.
"""

import json
import secrets
import ssl
import time
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import requests
from django.conf import settings
from django.db import close_old_connections, connection
from django.utils import timezone

from sii.accounts.models import CustomUser
from sii.assets.models import (
    Building,
    CalibrationRecord,
    Gateway,
    Sensor,
    SensorCommissioning,
    Zone,
)
from sii.monitoring.models import FreshnessPolicy
from sii.notifications.models import AlertContact, AlertRoute, Notification, NotificationAttempt
from sii.rules.models import RuleSet, RuleVersion
from sii.rules.services import activate, approve, backtest
from sii.tenants.models import Membership, Organisation, RoleAssignment, Site

from .models import ProcessingOutbox
from .security import provision, revoke
from .services import ingest


def prepare(run_id):
    """Construct a disjoint load-only demo tenant; approvals are explicitly software fixtures."""
    org = Organisation.objects.create(name="SYNTHETIC reference load " + str(run_id), is_demo=True)
    owner = CustomUser.objects.create_user(
        f"load-{run_id}@example.invalid", verified_at=timezone.now()
    )
    member = Membership.objects.create(organisation=org, user=owner)
    operator_password = secrets.token_urlsafe(32)
    operator = CustomUser.objects.create_user(
        f"load-operator-{run_id}@example.invalid", operator_password, verified_at=timezone.now()
    )
    operator_member = Membership.objects.create(organisation=org, user=operator)
    RoleAssignment.objects.create(organisation=org, membership=member, role="owner")
    prepared = []
    for index in range(20):
        site = Site.objects.create(organisation=org, name=f"SYNTHETIC load site {index:02}")
        scope = {"organisation": org, "site": site}
        RoleAssignment.objects.create(**scope, membership=member, role="qa")
        RoleAssignment.objects.create(**scope, membership=operator_member, role="operator")
        # Fictional local-capture recipient only; this is not customer consent evidence.
        contact = AlertContact.objects.create(
            **scope,
            user=operator,
            token_hash="",
            expires_at=timezone.now() + timedelta(hours=1),
            verified_at=timezone.now(),
        )
        AlertRoute.objects.create(
            **scope,
            name="SYNTHETIC benchmark TEST route",
            contact=contact,
            kinds=["too_warm"],
            severity="warning",
            timezone="Europe/Copenhagen",
            shift_start=0,
            shift_end=1440,
            created_by=owner,
        )
        building = Building.objects.create(**scope, name="Software-only facility")
        zone = Zone.objects.create(
            **scope, building=building, name="Synthetic zone", zone_type="test"
        )
        gateway = Gateway.objects.create(
            **scope, external_id=f"load-{index}", name="Synthetic gateway", state="commissioning"
        )
        sensors = [
            Sensor(
                **scope,
                zone=zone,
                gateway=gateway,
                external_id=f"load-{index}-{n}",
                name=f"Synthetic probe {n:02}",
                expected_interval_sec=60,
                state="commissioning",
                engineering_min=-100,
                engineering_max=150,
                capability_reference="SYNTHETIC load profile",
            )
            for n in range(40)
        ]
        # Fixed fixture data is constructed in exact scope; PostgreSQL still checks
        # every FK/uniqueness/range. This never grants real commissioning acceptance.
        Sensor.objects.bulk_create(sensors)
        now = timezone.now()
        CalibrationRecord.objects.bulk_create(
            [
                CalibrationRecord(
                    **scope,
                    sensor=s,
                    reference="SYNTHETIC reference, not physical calibration",
                    recorded_by=owner,
                    checked_at=now - timedelta(days=1),
                    due_at=now + timedelta(days=30),
                )
                for s in sensors
            ]
        )
        SensorCommissioning.objects.bulk_create(
            [
                SensorCommissioning(
                    **scope,
                    sensor=s,
                    technician_reference="SYNTHETIC",
                    placement_reference="Software fixture",
                    read_only_scope=True,
                    recorded_by=owner,
                )
                for s in sensors
            ]
        )
        FreshnessPolicy.objects.create(
            **scope,
            approved_by=owner,
            sensor_grace_sec=30,
            gateway_timeout_sec=180,
            sop_reference="SYNTHETIC cadence only",
            intervals={str(s.pk): 60 for s in sensors},
        )
        credential, secret = provision(gateway, owner, 1)
        for n in range(2):
            ingest(
                credential,
                {
                    "version": 1,
                    "event_id": str(uuid.uuid4()),
                    "sensor_id": str(sensors[0].pk),
                    "sequence": n,
                    "observed_at": (timezone.now() - timedelta(seconds=2 - n)).isoformat(),
                    "value": "4",
                    "unit": "degC",
                },
                "https",
            )
        family = RuleSet.objects.create(**scope, zone=zone, name="SYNTHETIC benchmark rule")
        version = RuleVersion.objects.create(
            **scope,
            ruleset=family,
            version=1,
            lower_bound=0,
            upper_bound=8,
            hysteresis=1,
            sustained_sec=60,
            recovery_sec=60,
            sop_reference="SYNTHETIC benchmark; never customer limits",
            created_by=owner,
        )
        test = backtest(version, owner, now - timedelta(minutes=1), timezone.now())
        activate(approve(version, test.pk, owner), owner)
        prepared.append((site, sensors, credential, secret))
    return org, owner, prepared, operator, operator_password


def percentile(values, percentile=0.95):
    """Use nearest-rank over completed samples; report missing work separately."""
    import math

    return sorted(values)[max(0, math.ceil(len(values) * percentile) - 1)] if values else None


def run(rounds=3):
    """Send one reading per probe per minute, collect durable receipts and actual processing lag."""
    if settings.ENVIRONMENT != "local" or connection.settings_dict["NAME"] != "sii_local":
        raise ValueError("Local synthetic database required")
    if not 3 <= rounds <= 10:
        raise ValueError("Choose 3..10 measured minutes")
    run_id = uuid.uuid4()
    print(json.dumps({"stage": "preparing", "run": str(run_id)}), flush=True)
    org, owner, prepared, operator, password = prepare(run_id)
    context = ssl.create_default_context(cafile="/tls-public/ca.crt")
    started = time.monotonic()
    base_time = timezone.now()
    ids, response_times, counts = (
        [],
        [],
        {"accepted": 0, "duplicate": 0, "rejected": 0, "errors": 0},
    )

    def send(index, round_number):
        """Use a bounded fixed-endpoint request; never print authentication/body failures."""
        site, sensors, credential, secret = prepared[index % 20]
        sensor = sensors[index // 20]
        event_id = uuid.uuid4()
        payload = {
            "version": 1,
            "event_id": str(event_id),
            "sensor_id": str(sensor.pk),
            "sequence": 100 + round_number,
            "observed_at": (
                base_time + timedelta(seconds=round_number * 60 + index * 60 / 800)
            ).isoformat(),
            "value": "12" if index % 10 == 0 and round_number > 0 else "4",
            "unit": "degC",
        }
        request = urllib.request.Request(
            "https://device-api:8443/api/v1/device/ingest/",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Device {credential.pk}.{secret}",
            },
        )
        before = time.monotonic()
        try:
            with urllib.request.urlopen(request, context=context, timeout=30) as response:
                result = json.load(response)[0]
            return str(event_id), result["status"], time.monotonic() - before
        except Exception:
            return str(event_id), "errors", time.monotonic() - before

    try:
        with ThreadPoolExecutor(max_workers=24) as executor:
            for round_number in range(rounds):
                futures = []
                for index in range(800):
                    target = started + round_number * 60 + index * 60 / 800
                    delay = target - time.monotonic()
                    if delay > 0:
                        time.sleep(delay)
                    futures.append(executor.submit(send, index, round_number))
                for future in futures:
                    identifier, status, elapsed = future.result()
                    ids.append(identifier)
                    counts[status] = counts.get(status, 0) + 1
                    response_times.append(elapsed)
                print(
                    json.dumps({"stage": "round", "round": round_number + 1, **counts}), flush=True
                )
        send_elapsed = time.monotonic() - started
        deadline = time.monotonic() + 180
        query = ProcessingOutbox.objects.filter(organisation=org, reading__event_id__in=ids)
        while query.filter(processed_at__isnull=True).exists() and time.monotonic() < deadline:
            time.sleep(2)
        rows = list(query.values_list("processed_at", "reading__received_at"))
        lags = [(done - received).total_seconds() for done, received in rows if done]
        # Exercise the real same-origin session/CSRF API as an ordinary operator.
        dashboard_times = []
        with requests.Session() as client:
            token = client.get("http://api:8000/api/v1/auth/csrf/", timeout=5).json()["csrf_token"]
            response = client.post(
                "http://api:8000/api/v1/auth/login/",
                json={"email": operator.email, "password": password},
                headers={"X-CSRFToken": token},
                timeout=10,
            )
            assert response.status_code == 200 and response.json()["state"] == "complete"
            for site, _, _, _ in prepared:
                before = time.monotonic()
                response = client.get(
                    f"http://api:8000/api/v1/organisations/{org.pk}/sites/{site.pk}/monitoring/",
                    timeout=10,
                )
                assert response.status_code == 200
                dashboard_times.append(time.monotonic() - before)
        deadline = time.monotonic() + 90
        expected_notifications = 80
        # Planning runs independently. An empty pending queue can mean the last
        # incident has not been planned yet, so await the known fictional outcomes
        # before revoking the fixture user/routes in finally.
        while (
            Notification.objects.filter(organisation=org, status="accepted").count()
            < expected_notifications
            and time.monotonic() < deadline
        ):
            time.sleep(1)
        notifications = list(
            NotificationAttempt.objects.filter(
                organisation=org, outcome="accepted", notification__event__incident__kind="too_warm"
            ).values_list("occurred_at", "notification__event__occurred_at")
        )
        notification_lags = [(done - at).total_seconds() for done, at in notifications]
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_total_relation_size('telemetry_reading')")
            reading_bytes = cursor.fetchone()[0]
        result = {
            "run": str(run_id),
            "organisation": str(org.pk),
            "sites": 20,
            "probes": 800,
            "minutes": rounds,
            "submitted": len(ids),
            **counts,
            "elapsed_send_sec": send_elapsed,
            # A slow sender is not evidence of the claimed one-minute cadence.
            "cadence_within_budget": send_elapsed <= rounds * 60 + 30,
            "late_backfill_readings": query.filter(
                reading__quality__contains=["late_backfill"]
            ).count(),
            "accepted_per_sec": counts["accepted"] / send_elapsed,
            "durable_accept_percent": counts["accepted"] * 100 / len(ids),
            "response_p95_sec": percentile(response_times),
            "processing_p95_sec": percentile(lags),
            "dashboard_p95_sec": percentile(dashboard_times),
            "dashboard_samples": len(dashboard_times),
            "notification_accept_p95_since_observation_sec": percentile(notification_lags),
            "accepted_notifications": len(notifications),
            "expected_notifications": expected_notifications,
            "processed": len(lags),
            "pending": len(rows) - len(lags),
            "reading_table_bytes_total": reading_bytes,
            "reference_daily_rate": 1152000,
            "actual_24h_soak": False,
        }
        print(json.dumps(result), flush=True)
        return result
    finally:
        for site, _, credential, _ in prepared:
            revoke(credential, owner)
            # Retire only this invocation's synthetic rig; retain every reading/incident.
            # Subsequent drills must not accidentally double the active reference load.
            Sensor.objects.filter(site=site, organisation=org).update(state="retired")
            Gateway.objects.filter(site=site, organisation=org).update(state="retired")
            AlertRoute.objects.filter(site=site, organisation=org).update(enabled=False)
        operator.is_active = False
        operator.save(update_fields=["is_active"])
        close_old_connections()
