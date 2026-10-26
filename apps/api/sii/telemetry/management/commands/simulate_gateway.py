"""Execute the local-only deterministic gateway acceptance workload."""

import json

from django.core.management.base import BaseCommand, CommandError

from sii.telemetry.simulator import run


class Command(BaseCommand):
    """Never accept remote endpoint, secret or customer identifiers as command arguments."""

    def add_arguments(self, parser):
        """Bound runtime/storage and permit reproducible seeded values."""
        parser.add_argument("--count", type=int, default=1000)
        parser.add_argument("--seed", type=int, default=42)

    def handle(self, *args, **options):
        """Print counts and non-secret evidence references only."""
        if not 100 <= options["count"] <= 10000:
            raise CommandError("Count must be 100..10000")
        self.stdout.write(json.dumps(run(options["count"], options["seed"])))
