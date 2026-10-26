"""Facility hierarchy and preserved qualification evidence, independently scoped to tenant/site."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from sii.tenants.models import Site, TenantModel


class Lifecycle(models.TextChoices):
    """Lifecycle is configuration, never a food-safety assessment."""

    PLANNED = "planned", "Planned"
    COMMISSIONING = "commissioning", "Commissioning"
    ACTIVE = "active", "Active"
    DEGRADED = "degraded", "Degraded"
    RETIRED = "retired", "Retired"


class ScopedAsset(TenantModel):
    """Immutable site anchor and reusable checks for all nested inventory/evidence references."""

    site = models.ForeignKey(Site, on_delete=models.PROTECT)

    class Meta:
        """Triple keys support PostgreSQL foreign keys enforcing both organisation and site."""

        abstract = True
        constraints = [
            models.UniqueConstraint(fields=["id", "organisation", "site"], name="%(class)s_scope")
        ]

    def clean(self):
        """Reject related inventory outside the exact site before ordinary ORM writes."""
        super().clean()
        if self.site.organisation_id != self.organisation_id:
            raise ValidationError("Site outside organisation.")
        for name in ["building", "zone", "gateway", "sensor", "commissioning"]:
            if getattr(self, name + "_id", None):
                related = getattr(self, name)
                if (related.organisation_id, related.site_id) != (
                    self.organisation_id,
                    self.site_id,
                ):
                    raise ValidationError("Related inventory outside site.")

    def save(self, *args, **kwargs):
        """Preserve hierarchy/identity anchors; moves require an explicit transfer protocol."""
        if not self._state.adding:
            old = type(self).objects.get(pk=self.pk)
            for field in [
                "site_id",
                "building_id",
                "zone_id",
                "gateway_id",
                "sensor_id",
                "external_id",
            ]:
                if getattr(old, field, None) != getattr(self, field, None):
                    raise ValidationError("Inventory scope is immutable.")
        super().save(*args, **kwargs)


class Building(ScopedAsset):
    """Named facility within a site; archiving preserves device/history references."""

    name = models.CharField(max_length=160)
    archived = models.BooleanField(default=False)

    class Meta(ScopedAsset.Meta):
        """Require unambiguous building names in a site."""

        constraints = [
            *ScopedAsset.Meta.constraints,
            models.UniqueConstraint(fields=["site", "name"], name="building_site_name"),
        ]


class Zone(ScopedAsset):
    """Room/zone records describe SOP context; their category never chooses a threshold."""

    building = models.ForeignKey(Building, on_delete=models.PROTECT)
    name = models.CharField(max_length=160)
    zone_type = models.CharField(max_length=40)
    sop_reference = models.CharField(max_length=240, blank=True)
    criticality = models.CharField(
        max_length=20,
        choices=[("unreviewed", "Unreviewed"), ("standard", "Standard"), ("critical", "Critical")],
        default="unreviewed",
    )
    archived = models.BooleanField(default=False)

    class Meta(ScopedAsset.Meta):
        """Disambiguate zone names inside each building."""

        constraints = [
            *ScopedAsset.Meta.constraints,
            models.UniqueConstraint(fields=["building", "name"], name="zone_building_name"),
        ]


class Gateway(ScopedAsset):
    """Read-only gateway inventory; telemetry owns separate expiring device credentials."""

    external_id = models.CharField(max_length=120)
    name = models.CharField(max_length=160)
    firmware_version = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=20, choices=Lifecycle.choices, default=Lifecycle.PLANNED)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta(ScopedAsset.Meta):
        """Unique gateway identity within the customer; no arbitrary lifecycle values."""

        constraints = [
            *ScopedAsset.Meta.constraints,
            models.UniqueConstraint(
                fields=["organisation", "external_id"], name="gateway_external"
            ),
            models.CheckConstraint(
                condition=models.Q(state__in=Lifecycle.values), name="gateway_state"
            ),
        ]


class Sensor(ScopedAsset):
    """Fixed zone/gateway assignment with explicit units and cadence, not safety limits."""

    zone = models.ForeignKey(Zone, on_delete=models.PROTECT)
    gateway = models.ForeignKey(Gateway, on_delete=models.PROTECT)
    external_id = models.CharField(max_length=120)
    name = models.CharField(max_length=160)
    sensor_type = models.CharField(max_length=40, default="temperature")
    unit = models.CharField(max_length=12, choices=[("degC", "Celsius")], default="degC")
    expected_interval_sec = models.PositiveIntegerField()
    # Physical range/capability evidence is independent of customer-approved alarm rules.
    engineering_min = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    engineering_max = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    capability_reference = models.CharField(max_length=240, blank=True)
    state = models.CharField(max_length=20, choices=Lifecycle.choices, default=Lifecycle.PLANNED)

    class Meta(ScopedAsset.Meta):
        """Preserve unique source identity and bounded nonzero expected intervals."""

        constraints = [
            *ScopedAsset.Meta.constraints,
            models.UniqueConstraint(fields=["organisation", "external_id"], name="sensor_external"),
            models.CheckConstraint(
                condition=models.Q(state__in=Lifecycle.values), name="sensor_state"
            ),
            models.CheckConstraint(
                condition=models.Q(expected_interval_sec__gte=1, expected_interval_sec__lte=86400),
                name="sensor_interval",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(engineering_min__isnull=True, engineering_max__isnull=True)
                    | models.Q(engineering_min__lt=models.F("engineering_max"))
                ),
                name="sensor_engineering_range",
            ),
        ]


class CalibrationRecord(ScopedAsset):
    """Append-only reference metadata; synthetic records never certify real calibration."""

    sensor = models.ForeignKey(Sensor, on_delete=models.PROTECT, related_name="calibrations")
    reference = models.CharField(max_length=240)
    checked_at = models.DateTimeField()
    due_at = models.DateTimeField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    synthetic = models.BooleanField(default=True, editable=False)

    class Meta(ScopedAsset.Meta):
        """Reject impossible calibration validity ranges, including bulk writes."""

        constraints = [
            *ScopedAsset.Meta.constraints,
            models.CheckConstraint(
                condition=models.Q(due_at__gt=models.F("checked_at")), name="calibration_dates"
            ),
        ]


class SensorCommissioning(ScopedAsset):
    """Preserved installation/placement draft with a responsible-person reference."""

    sensor = models.ForeignKey(Sensor, on_delete=models.PROTECT, related_name="commissionings")
    technician_reference = models.CharField(max_length=240)
    placement_reference = models.CharField(max_length=240)
    read_only_scope = models.BooleanField(default=False)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)
    synthetic = models.BooleanField(default=True, editable=False)


class SiteCommissioning(ScopedAsset):
    """Append-only responsibility/contingency pack; each amendment is another draft."""

    customer_approval_reference = models.CharField(max_length=240, blank=True)
    contingency_reference = models.CharField(max_length=240, blank=True)
    responsible_person = models.CharField(max_length=240)
    read_only_scope = models.BooleanField(default=False)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)
    synthetic = models.BooleanField(default=True, editable=False)


class CommissioningTest(ScopedAsset):
    """Append-only manually recorded drill evidence, explicitly synthetic in this environment."""

    commissioning = models.ForeignKey(
        SiteCommissioning, on_delete=models.PROTECT, related_name="tests"
    )
    kind = models.CharField(
        max_length=30,
        choices=[(name, name) for name in ["sensor_feed", "breach", "no_data", "routing"]],
    )
    passed = models.BooleanField()
    evidence_reference = models.CharField(max_length=240)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)
    synthetic = models.BooleanField(default=True, editable=False)


class CommissioningAcceptance(ScopedAsset):
    """QA review of a specific pack/sensor snapshot; cannot itself enable monitoring."""

    commissioning = models.ForeignKey(SiteCommissioning, on_delete=models.PROTECT)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    approved_at = models.DateTimeField(auto_now_add=True)
    evidence_hash = models.CharField(max_length=64)
    evidence_snapshot = models.JSONField(default=dict, editable=False)
    synthetic = models.BooleanField(default=True, editable=False)

    class Meta(ScopedAsset.Meta):
        """Only one acceptance per versioned commissioning pack."""

        constraints = [
            *ScopedAsset.Meta.constraints,
            models.UniqueConstraint(fields=["commissioning"], name="commissioning_once"),
        ]
