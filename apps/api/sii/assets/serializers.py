"""Inventory contracts protect ownership, lifecycle, actor and approval flags."""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from sii.audit.services import digest
from sii.tenants.serializers import StrictInputMixin

from . import models
from .services import pack_evidence, sensor_qualification


class InventorySerializer(StrictInputMixin, serializers.ModelSerializer):
    """Shared immutable anchor fields; services validate all related UUIDs in the exact scope."""

    class Meta:
        """Only explicit fields are writable; DB/model validation supplies scope."""

        fields = ["id", "organisation", "site"]
        read_only_fields = fields
        validators = []


class BuildingSerializer(InventorySerializer):
    """Named building with reversible archive; no hard deletion API."""

    class Meta(InventorySerializer.Meta):
        """Building metadata contract."""

        model = models.Building
        fields = [*InventorySerializer.Meta.fields, "name", "archived"]


class ZoneSerializer(InventorySerializer):
    """Building UUID is resolved only within the URL site; categories imply no safe limits."""

    building = serializers.UUIDField(source="building_id")

    class Meta(InventorySerializer.Meta):
        """Zone configuration, with fixed hierarchy after registration."""

        model = models.Zone
        fields = [
            *InventorySerializer.Meta.fields,
            "building",
            "name",
            "zone_type",
            "sop_reference",
            "criticality",
            "archived",
        ]


class GatewaySerializer(InventorySerializer):
    """Gateway configuration excludes credentials and derives state from transition commands."""

    class Meta(InventorySerializer.Meta):
        """Heartbeat/state cannot be spoofed by configuration payloads."""

        model = models.Gateway
        fields = [
            *InventorySerializer.Meta.fields,
            "external_id",
            "name",
            "firmware_version",
            "state",
            "last_heartbeat_at",
        ]
        read_only_fields = [
            *InventorySerializer.Meta.read_only_fields,
            "state",
            "last_heartbeat_at",
        ]


class QualificationSerializer(serializers.Serializer):
    """Current evidence state; warnings are explicit codes localized by the portal."""

    calibration_status = serializers.CharField()
    calibration_due_at = serializers.DateTimeField(allow_null=True)
    calibration_id = serializers.UUIDField(allow_null=True)
    installation_id = serializers.UUIDField(allow_null=True)
    warnings = serializers.ListField(child=serializers.CharField())
    synthetic = serializers.BooleanField()


class SensorSerializer(InventorySerializer):
    """Sensor inventory includes current calibration warnings, never an invented reading."""

    zone = serializers.UUIDField(source="zone_id")
    gateway = serializers.UUIDField(source="gateway_id")
    qualification = serializers.SerializerMethodField()

    @extend_schema_field(QualificationSerializer)
    def get_qualification(self, sensor):
        """Evaluate expiry at response time instead of preserving stale green metadata."""
        return QualificationSerializer(sensor_qualification(sensor)).data

    class Meta(InventorySerializer.Meta):
        """Ownership/lifecycle remain command-controlled; interval is bounded in model/DB."""

        model = models.Sensor
        fields = [
            *InventorySerializer.Meta.fields,
            "zone",
            "gateway",
            "external_id",
            "name",
            "sensor_type",
            "unit",
            "expected_interval_sec",
            "engineering_min",
            "engineering_max",
            "capability_reference",
            "state",
            "qualification",
        ]
        read_only_fields = [*InventorySerializer.Meta.read_only_fields, "state", "qualification"]


class EvidenceSerializer(InventorySerializer):
    """Evidence is created once, never edited; actor/time/provenance are server-controlled."""

    class Meta(InventorySerializer.Meta):
        """All development evidence is marked synthetic and cannot certify physical devices."""

        fields = [*InventorySerializer.Meta.fields, "recorded_by", "synthetic"]
        read_only_fields = fields


class CalibrationSerializer(EvidenceSerializer):
    """Append-only calibration reference/validity metadata; no uploaded document in Sprint 03."""

    sensor = serializers.UUIDField(source="sensor_id")

    class Meta(EvidenceSerializer.Meta):
        """The recording service checks dates and exact sensor scope."""

        model = models.CalibrationRecord
        fields = [*EvidenceSerializer.Meta.fields, "sensor", "reference", "checked_at", "due_at"]


class SensorCommissioningSerializer(EvidenceSerializer):
    """Installation draft records responsible technician, placement and read-only intent."""

    sensor = serializers.UUIDField(source="sensor_id")

    class Meta(EvidenceSerializer.Meta):
        """Recorded timestamp belongs to the server clock."""

        model = models.SensorCommissioning
        fields = [
            *EvidenceSerializer.Meta.fields,
            "sensor",
            "technician_reference",
            "placement_reference",
            "read_only_scope",
            "recorded_at",
        ]
        read_only_fields = [*EvidenceSerializer.Meta.read_only_fields, "recorded_at"]


class SiteCommissioningSerializer(EvidenceSerializer):
    """Versioned site pack exposes current missing qualification warnings."""

    warnings = serializers.SerializerMethodField()

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_warnings(self, pack):
        """Refresh prerequisites after device, calibration or test changes."""
        return pack_evidence(pack)[1]

    class Meta(EvidenceSerializer.Meta):
        """A new pack amends responsibility/acceptance references without rewriting history."""

        model = models.SiteCommissioning
        fields = [
            *EvidenceSerializer.Meta.fields,
            "customer_approval_reference",
            "contingency_reference",
            "responsible_person",
            "read_only_scope",
            "recorded_at",
            "warnings",
        ]
        read_only_fields = [*EvidenceSerializer.Meta.read_only_fields, "recorded_at", "warnings"]


class CommissioningTestSerializer(EvidenceSerializer):
    """Record the result and reference of a specific synthetic commissioning drill."""

    commissioning = serializers.UUIDField(source="commissioning_id")

    class Meta(EvidenceSerializer.Meta):
        """These manually recorded drills do not stand in for future real transport/alert tests."""

        model = models.CommissioningTest
        fields = [
            *EvidenceSerializer.Meta.fields,
            "commissioning",
            "kind",
            "passed",
            "evidence_reference",
            "recorded_at",
        ]
        read_only_fields = [*EvidenceSerializer.Meta.read_only_fields, "recorded_at"]


class AcceptanceSerializer(InventorySerializer):
    """Read-only QA review result, including evidence snapshot hash and synthetic marker."""

    current = serializers.SerializerMethodField()

    @extend_schema_field(serializers.BooleanField())
    def get_current(self, acceptance):
        """Never imply an old acceptance still covers changed configuration or expired evidence."""
        evidence, warnings = pack_evidence(acceptance.commissioning)
        return not warnings and acceptance.evidence_hash == digest(evidence)

    class Meta(InventorySerializer.Meta):
        """Acceptance creation is a separate QA-only command."""

        model = models.CommissioningAcceptance
        fields = [
            *InventorySerializer.Meta.fields,
            "commissioning",
            "approved_by",
            "approved_at",
            "evidence_hash",
            "synthetic",
            "evidence_snapshot",
            "current",
        ]
        read_only_fields = fields


class TransitionInput(StrictInputMixin, serializers.Serializer):
    """Request a lifecycle transition, not arbitrary model field writes."""

    target = serializers.ChoiceField(choices=models.Lifecycle.choices)


class ActivationResult(serializers.Serializer):
    """Explicit unmet gates for site activation; no boolean is represented as a safety decision."""

    blockers = serializers.ListField(child=serializers.CharField())
