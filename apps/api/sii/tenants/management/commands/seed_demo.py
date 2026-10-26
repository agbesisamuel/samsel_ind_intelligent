"""Seed two isolated fictional organisations without globally known passwords or MFA bypass."""

import os
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from sii.accounts.models import CustomUser
from sii.assets.models import Building, Gateway, Sensor, Zone
from sii.audit.services import record
from sii.tenants.models import Membership, Organisation, Role, RoleAssignment, Site


def demo_id(name):
    """Use a stable reserved namespace so reruns never select arbitrary customer records by name."""
    return uuid.uuid5(uuid.NAMESPACE_URL, "https://example.invalid/sii-demo/" + name)


class Command(BaseCommand):
    """Create new fixtures only; never overwrite existing credentials, scopes or audit history."""

    help = "Seed local fictional tenants; passwords come only from generated local environment."

    @transaction.atomic
    def handle(self, *args, **options):
        """Refuse non-local environments and seed disabled-monitoring, MFA-required owners."""
        if settings.ENVIRONMENT != "local" or settings.DATABASES["default"]["NAME"] != "sii_local":
            raise CommandError("Only the local synthetic database is permitted.")
        for label in ["A", "B", "PLATFORM", "OPERATOR"]:
            password = os.environ.get(f"DEMO_{label}_PASSWORD", "")
            if len(password) < 32 or "GENERATE_LOCALLY" in password:
                raise CommandError("Run setup to generate local demo credentials.")
        for label in ["A", "B"]:
            org, created = Organisation.objects.get_or_create(
                id=demo_id(label),
                defaults={"name": f"Fictional {label} — synthetic only", "is_demo": True},
            )
            if not org.is_demo:
                raise CommandError("Reserved demo ID collision; refusing to alter existing data.")
            if created:
                record("demo.organisation_created", organisation=org, subject=org.pk)
            sites = []
            for index in [1, 2]:
                site, _ = Site.objects.get_or_create(
                    id=demo_id(f"{label}/site/{index}"),
                    defaults={"organisation": org, "name": f"Fictional site {label}{index}"},
                )
                if site.organisation_id != org.pk:
                    raise CommandError("Demo site ownership mismatch.")
                sites.append(site)
                self.create_inventory(site, f"{label}/{index}")
            self.create_person(f"owner-{label.lower()}@example.invalid", label, org, Role.OWNER)
            if label == "A":
                self.create_person(
                    "operator@example.invalid", "OPERATOR", org, Role.OPERATOR, sites[0]
                )
        self.create_person("platform@example.invalid", "PLATFORM", platform=True)
        self.stdout.write(
            "Fictional tenants A/B seeded. Passwords stay in .env; "
            "owners/platform require MFA enrollment."
        )

    def create_person(self, email, key, organisation=None, role=None, site=None, platform=False):
        """Create reserved synthetic identities without adopting existing customer accounts."""
        user, created = CustomUser.objects.get_or_create(
            id=demo_id(email),
            defaults={
                "email": email,
                "verified_at": timezone.now(),
                "is_staff": platform,
                "is_superuser": platform,
            },
        )
        if user.email != email:
            raise CommandError("Reserved demo identity collision.")
        if not created:
            return
        user.set_password(os.environ[f"DEMO_{key}_PASSWORD"])
        user.save()
        if organisation:
            member = Membership.objects.create(organisation=organisation, user=user)
            RoleAssignment.objects.create(
                organisation=organisation, membership=member, role=role, site=site
            )
        record(
            "demo.identity_created",
            actor=user,
            organisation=organisation,
            site=site,
            subject=user.pk,
        )

    def create_inventory(self, site, label):
        """Seed planned synthetic devices only; never invent calibration, tests or acceptance."""
        scope = {"organisation": site.organisation, "site": site}
        building, _ = Building.objects.get_or_create(
            id=demo_id(label + "/building"), defaults={**scope, "name": "Synthetic building"}
        )
        zone, _ = Zone.objects.get_or_create(
            id=demo_id(label + "/zone"),
            defaults={
                **scope,
                "building": building,
                "name": "Synthetic cold room",
                "zone_type": "cold_room",
            },
        )
        gateway, _ = Gateway.objects.get_or_create(
            id=demo_id(label + "/gateway"),
            defaults={**scope, "external_id": "synthetic-" + label, "name": "Simulator gateway"},
        )
        sensor, created = Sensor.objects.get_or_create(
            id=demo_id(label + "/sensor"),
            defaults={
                **scope,
                "zone": zone,
                "gateway": gateway,
                "external_id": "synthetic-" + label,
                "name": "Synthetic temperature probe",
                "expected_interval_sec": 60,
            },
        )
        for item in [building, zone, gateway, sensor]:
            if item.organisation_id != site.organisation_id or item.site_id != site.pk:
                raise CommandError("Reserved demo inventory scope mismatch.")
        if created:
            record(
                "demo.inventory_created",
                organisation=site.organisation,
                site=site,
                subject=sensor.pk,
            )
