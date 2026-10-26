"""Prove durable SDK buffering/reopen/replay through the actual local TLS device API."""

import json
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from sii.adapters.sdk import ReplayBuffer, Sample, SyntheticAdapter
from sii.telemetry.security import provision, revoke
from sii.telemetry.simulator import http, prepare


class Command(BaseCommand):
    """Accept no hardware address or remote destination; target only reserved synthetic fixtures."""

    def handle(self, *args, **options):
        """Persist source clocks, reopen after a simulated gap and prove duplicate receipts."""
        if settings.ENVIRONMENT != "local":
            raise CommandError("Synthetic local-only drill")
        sensor, actor = prepare()
        run = uuid.uuid4()
        path = Path("/simulator") / f"adapter-{run}.sqlite3"
        now = timezone.now()
        sequence = int(now.timestamp() * 1_000_000)
        adapter = SyntheticAdapter(
            [
                Sample(sensor.pk, sequence + n, now - timedelta(seconds=20 - n), Decimal(value))
                for n, value in enumerate(["0", "4", "12"])
            ]
        )
        with ReplayBuffer(path, sensor.gateway_id) as buffer:
            for sample in adapter.samples():
                buffer.enqueue(sample)
            buffer.discontinuity(now - timedelta(seconds=15), now - timedelta(seconds=5))
        credential, secret = provision(sensor.gateway, actor, 1)
        try:
            with ReplayBuffer(path, sensor.gateway_id) as buffer:
                events = buffer.pending()
                for event in events:
                    receipt = http(credential, secret, payload=event)[0]
                    buffer.acknowledge(event["event_id"], receipt)
                    repeated = http(credential, secret, payload=event)[0]
                    assert repeated["status"] == "duplicate"
                assert buffer.pending() == []
            self.stdout.write(
                json.dumps(
                    {
                        "synthetic": True,
                        "buffered": 3,
                        "accepted": 3,
                        "duplicates": 3,
                        "pending": 0,
                        "run": str(run),
                        "live_enabled": False,
                    }
                )
            )
        finally:
            revoke(credential, actor)
