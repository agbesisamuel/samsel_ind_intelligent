"""Independent bounded report generation; stale leases remain visible for explicit retry."""

import time
from pathlib import Path

from django.core.management.base import BaseCommand

from sii.reports.services import tick


class Command(BaseCommand):
    """A failed infrastructure scheduling pass exits for supervised restart."""

    def handle(self, *args, **options):
        """Heartbeat only after a complete bounded generation pass."""
        while True:
            tick()
            Path("/tmp/report-heartbeat").touch()
            time.sleep(5)
