"""Explicit immutable tenant ownership; PostgreSQL also guards bulk/raw write boundaries."""

import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


def validate_timezone(value):
    """Reject unknown IANA zones rather than silently rendering customer time as UTC."""
    try:
        ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise ValidationError("Use an IANA timezone.") from exc


class Organisation(models.Model):
    """Customer boundary; contract state never enables monitoring by itself."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    country_code = models.CharField(max_length=2, default="DK")
    timezone_default = models.CharField(
        max_length=64, default="Europe/Copenhagen", validators=[validate_timezone]
    )
    contract_status = models.CharField(max_length=20, default="draft", editable=False)
    is_demo = models.BooleanField(default=False, editable=False)


class TenantModel(models.Model):
    """Tenant anchor for services and workers; save rejects ownership transfer."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(Organisation, on_delete=models.PROTECT)

    class Meta:
        """Share fields without creating a polymorphic customer-data table."""

        abstract = True

    def save(self, *args, **kwargs):
        """Validate related tenant ownership and stable org IDs on ordinary writes."""
        if not self._state.adding:
            old = type(self).objects.get(pk=self.pk)
            if old.organisation_id != self.organisation_id:
                raise ValidationError("Organisation ownership is immutable.")
        self.full_clean()
        super().save(*args, **kwargs)


class Site(TenantModel):
    """A site's scope and timezone exist before any monitoring can be commissioned."""

    name = models.CharField(max_length=160)
    timezone = models.CharField(
        max_length=64, default="Europe/Copenhagen", validators=[validate_timezone]
    )
    service_state = models.CharField(max_length=20, default="planned", editable=False)
    archived = models.BooleanField(default=False)

    class Meta:
        """Disambiguate names within an organisation and support composite foreign keys."""

        constraints = [
            models.UniqueConstraint(fields=["organisation", "name"], name="site_org_name_unique"),
            models.UniqueConstraint(fields=["id", "organisation"], name="site_id_org_unique"),
        ]


class Membership(TenantModel):
    """Active organisation membership alone confers no site or management permission."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    active = models.BooleanField(default=True)

    class Meta:
        """Prevent duplicate membership identities and support tenant-safe role references."""

        constraints = [
            models.UniqueConstraint(fields=["organisation", "user"], name="membership_org_user"),
            models.UniqueConstraint(fields=["id", "organisation"], name="membership_id_org"),
        ]


class Role(models.TextChoices):
    """Roles are independent; QA approval is never implied by site administration."""

    OWNER = "owner", "Organisation owner"
    SITE_ADMIN = "site_admin", "Site administrator"
    QA = "qa", "QA manager"
    OPERATIONS = "operations", "Operations manager"
    OPERATOR = "operator", "On-call operator"
    AUDITOR = "auditor", "Read-only auditor"


class RoleAssignment(TenantModel):
    """Only owners have organisation-wide scope; all other roles require an exact site."""

    membership = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name="roles")
    site = models.ForeignKey(Site, null=True, blank=True, on_delete=models.PROTECT)
    role = models.CharField(max_length=20, choices=Role.choices)

    class Meta:
        """Enforce one assignment per scope and reject implicit organisation-wide roles."""

        constraints = [
            models.UniqueConstraint(
                fields=["membership", "site", "role"],
                nulls_distinct=False,
                name="role_membership_site_unique",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(role="owner", site__isnull=True)
                    | (~models.Q(role="owner") & models.Q(site__isnull=False))
                ),
                name="role_exact_scope",
            ),
            models.CheckConstraint(condition=models.Q(role__in=Role.values), name="role_known"),
        ]

    def clean(self):
        """Reject nested foreign identifiers even when called by a background service."""
        if self.membership.organisation_id != self.organisation_id:
            raise ValidationError("Membership is outside scope.")
        if self.site_id and self.site.organisation_id != self.organisation_id:
            raise ValidationError("Site is outside scope.")


class Invitation(TenantModel):
    """Email proof and exact offered role; plaintext random tokens are never persisted."""

    email = models.EmailField()
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    site = models.ForeignKey(Site, null=True, blank=True, on_delete=models.PROTECT)
    role = models.CharField(max_length=20, choices=Role.choices)

    class Meta:
        """Invitation scopes obey the same boundary as persisted role assignments."""

        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(role="owner", site__isnull=True)
                    | (~models.Q(role="owner") & models.Q(site__isnull=False))
                ),
                name="invite_exact_scope",
            ),
            models.CheckConstraint(
                condition=models.Q(role__in=Role.values), name="invite_role_known"
            ),
        ]

    def clean(self):
        """Validate scoped site ownership before a token can be issued."""
        if self.site_id and self.site.organisation_id != self.organisation_id:
            raise ValidationError("Site is outside scope.")
