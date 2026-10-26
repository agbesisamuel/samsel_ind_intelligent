"""Run local telemetry bootstrap/consumer and bounded administrative replay."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from sii.audit.services import record
from sii.telemetry.models import ProcessingOutbox
from sii.telemetry.transport import bootstrap, run_group, run_publisher, run_worker


class Command(BaseCommand):
    """Separate process has durable broker queues and a DB outbox; restart never clears either."""

    def add_arguments(self, parser):
        """Replay requires an explicit local flag and a hard batch bound."""
        parser.add_argument("action", choices=["bootstrap", "run", "group", "publish", "replay"])
        parser.add_argument("--confirm-local", action="store_true")
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--shard", type=int, choices=range(16), default=0)
        parser.add_argument("--group", type=int, choices=range(4), default=0)

    def handle(self, *args, **options):
        """Never select remote/customer datasets from command line arguments."""
        if settings.ENVIRONMENT != "local":
            raise CommandError("Local only")
        if options["action"] == "bootstrap":
            bootstrap()
            self.stdout.write("Telemetry topology ready")
        elif options["action"] == "run":
            run_worker(options["shard"])
        elif options["action"] == "publish":
            run_publisher()
        elif options["action"] == "group":
            run_group(options["group"])
        else:
            if not options["confirm_local"] or not 1 <= options["limit"] <= 100:
                raise CommandError("Replay needs --confirm-local and limit 1..100")
            items = list(
                ProcessingOutbox.objects.filter(
                    dead_lettered=True, processed_at__isnull=True, organisation__is_demo=True
                ).order_by("id")[: options["limit"]]
            )
            for item in items:
                item.dead_lettered, item.attempts, item.available_at = False, 0, timezone.now()
                item.save(update_fields=["dead_lettered", "attempts", "available_at"])
                record(
                    "telemetry.local_replay",
                    organisation=item.organisation,
                    site=item.site,
                    subject=item.pk,
                )
            self.stdout.write(f"Requeued {len(items)} synthetic outbox records")
