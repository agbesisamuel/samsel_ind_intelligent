"""Run the internal versioned domain-event collector, publisher and receipt consumer."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from sii.audit.services import record
from sii.events.models import DomainEvent
from sii.events.services import run


class Command(BaseCommand):
    """Crash on infrastructure failure; committed source evidence remains recoverable."""

    def add_arguments(self, parser):
        """Replay is explicit, bounded and restricted to synthetic local evidence."""
        parser.add_argument("--replay-local", action="store_true")
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        """Use fixed private broker topology; no caller-controlled endpoints or tenant overrides."""
        if options["replay_local"]:
            if settings.ENVIRONMENT != "local" or not 1 <= options["limit"] <= 100:
                raise CommandError("Replay requires local environment and limit 1..100")
            events = list(
                DomainEvent.objects.filter(
                    organisation__is_demo=True, dead_lettered=True, consumed_at__isnull=True
                ).order_by("id")[: options["limit"]]
            )
            for event in events:
                DomainEvent.objects.filter(pk=event.pk).update(
                    dead_lettered=False, attempts=0, available_at=timezone.now()
                )
                record(
                    "domain.local_replay",
                    organisation=event.organisation,
                    site=event.site,
                    subject=event.pk,
                )
            self.stdout.write(f"Requeued {len(events)} synthetic domain events")
            return
        run()
