"""Shared isolated two-tenant fixtures; no production identities or force-authentication."""

import secrets
from importlib import import_module

import pytest
from django.apps import apps
from django.db import connection
from django.utils import timezone

from sii.accounts.models import CustomUser
from sii.tenants.models import Membership, Organisation, Role, RoleAssignment, Site


class FixtureSecret(str):
    """Keep ephemeral fixture passwords out of pytest's argument/dictionary failure display."""

    def __repr__(self):
        """Return a non-secret label while normal string encoding still authenticates tests."""
        return "<redacted fixture secret>"


@pytest.fixture
def world():
    """Build two disjoint organisations with two sites each and separate real user identities."""
    from sii.billing.models import Plan

    # Transactional concurrency tests flush reference data. Restore the empty
    # synthetic catalog from its owned migration, never disable immutable guards
    # or deserialize over existing rows (which would attempt forbidden UPDATEs).
    assert connection.settings_dict["NAME"].startswith("test_")
    if not Plan.objects.exists():
        import_module("sii.billing.migrations.0002_local_plans_and_guards").seed(apps, None)
    password = FixtureSecret(secrets.token_urlsafe(32))
    result = {"password": password}
    for label in ["a", "b"]:
        # General tenancy scenarios use the explicit synthetic development plan;
        # quota-specific tests select constrained templates and exercise raw SQL too.
        org = Organisation.objects.create(name=f"Fictional {label}", is_demo=True)
        sites = [Site.objects.create(organisation=org, name=f"{label}{i}") for i in [1, 2]]
        user = CustomUser.objects.create_user(
            f"{label}@example.invalid", password, verified_at=timezone.now()
        )
        member = Membership.objects.create(organisation=org, user=user)
        RoleAssignment.objects.create(organisation=org, membership=member, role=Role.OWNER)
        result[label] = {"org": org, "sites": sites, "user": user, "member": member}
    return result
