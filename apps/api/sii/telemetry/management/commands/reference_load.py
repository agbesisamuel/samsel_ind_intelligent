"""Run the fixed local reference workload; no arbitrary external destination is accepted."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from sii.telemetry.reference_load import run


class Command(BaseCommand):
    """Retain measured non-secret results in container scratch for review."""

    def handle(self, *args, **options):
        """Run three real cadence rounds and preserve counts/latency including failures."""
        result = run()
        Path("/tmp/sii-reference-load.json").write_text(json.dumps(result, indent=2))
        # Preserve failures before rejecting the engineering gate. This short run
        # does not turn local performance into a cloud availability/SLA assertion.
        if (
            result["durable_accept_percent"] < 99.9
            or not result["cadence_within_budget"]
            or result["late_backfill_readings"]
            or result["pending"]
            or result["processing_p95_sec"] is None
            or result["processing_p95_sec"] > 15
            or result["dashboard_p95_sec"] > 2
            or result["accepted_notifications"] != result["expected_notifications"]
        ):
            raise CommandError(
                "Reference targets not met; retained measured results require review"
            )
