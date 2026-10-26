"""Evaluate sensor and gateway failures even when no ingestion events arrive."""

import time
from pathlib import Path

from django.core.management.base import BaseCommand

from sii.assets.models import Sensor
from sii.monitoring.services import refresh_sensor
from sii.rules.services import evaluate_health


class Command(BaseCommand):
    """Independent process, restartable from durable records, with a bounded heartbeat deadline."""

    def add_arguments(self, parser):
        """Support one-shot local verification without starting a daemon."""
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        """Refresh all scoped projections; a storage error exits so health cannot remain green."""
        while True:
            for sensor_id in (
                Sensor.objects.exclude(state="retired")
                .values_list("id", flat=True)
                .iterator(chunk_size=100)
            ):
                # Evaluate after the projection transaction releases its sensor lock.
                # Incident services use gateway-first locks, as does ingestion.
                projection = refresh_sensor(sensor_id)
                evaluate_health(projection)
            Path("/tmp/freshness-heartbeat").touch()
            if options["once"]:
                return
            time.sleep(15)
