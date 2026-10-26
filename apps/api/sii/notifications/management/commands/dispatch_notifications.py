"""Independent durable notification dispatcher; no incoming telemetry needed for escalation."""

import time
from pathlib import Path

from django.core.cache import cache
from django.core.management.base import BaseCommand

from sii.notifications.services import tick


class Command(BaseCommand):
    """Report health only after a complete scheduling/delivery pass; infrastructure faults exit."""

    def add_arguments(self, parser):
        """Expose one-shot operation for local acceptance checks."""
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        """Poll durable state with bounded batches; worker crashes preserve pending attempts."""
        while True:
            tick()
            cache.set("notification-worker-alive", True, timeout=90)
            Path("/tmp/notification-heartbeat").touch()
            if options["once"]:
                return
            time.sleep(5)
