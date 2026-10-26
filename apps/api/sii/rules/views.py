"""Audited rule draft/test/approve/activate commands with independent QA authority."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from sii.accounts.security import step_up
from sii.accounts.views import inputs
from sii.assets.models import Sensor, Zone
from sii.assets.services import require_qa
from sii.audit.services import record
from sii.telemetry.contracts import TimeWindow
from sii.telemetry.views import TelemetryView
from sii.tenants.access import sites_for
from sii.tenants.models import Role, Site
from sii.tenants.serializers import StrictInputMixin

from . import models, services


class FamilySerializer(StrictInputMixin, serializers.ModelSerializer):
    """Zone references are resolved in the URL site before creating a single rule family."""

    zone = serializers.UUIDField(source="zone_id")

    class Meta:
        """Only name and zone are writable; scope is derived from current grants."""

        model = models.RuleSet
        fields = ["id", "zone", "name"]
        read_only_fields = ["id"]
        validators = []


class VersionSerializer(StrictInputMixin, serializers.ModelSerializer):
    """Immutable version content with a derived lifecycle, never a mutable approved draft."""

    ruleset = serializers.UUIDField(source="ruleset_id")
    stage = serializers.SerializerMethodField()
    latest_backtest = serializers.SerializerMethodField()
    approval = serializers.SerializerMethodField()

    @extend_schema_field(serializers.CharField())
    def get_stage(self, version):
        """Derive supersession from immutable effective boundaries."""
        approval = models.RuleApproval.objects.filter(version=version).first()
        if approval:
            active = (
                models.RuleActivation.objects.filter(ruleset=version.ruleset)
                .order_by("-effective_at")
                .first()
            )
            if active and active.approval_id == approval.pk:
                return "active_synthetic"
            if models.RuleActivation.objects.filter(approval=approval).exists():
                return "superseded"
            return "approved"
        return "tested" if models.RuleBacktest.objects.filter(version=version).exists() else "draft"

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_latest_backtest(self, version):
        """Expose a same-version preview reference for explicit QA review."""
        return (
            models.RuleBacktest.objects.filter(version=version)
            .order_by("-created_at")
            .values_list("id", flat=True)
            .first()
        )

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_approval(self, version):
        """Expose an approval identifier, never infer QA permission from it."""
        return (
            models.RuleApproval.objects.filter(version=version).values_list("id", flat=True).first()
        )

    def validate(self, data):
        """Enforce finite ordered bounds, a meaningful hysteresis band and bounded durations."""
        if not data["lower_bound"] < data["upper_bound"]:
            raise ValidationError("Lower bound must be below upper bound.")
        if not 0 <= data["hysteresis"] < (data["upper_bound"] - data["lower_bound"]) / 2:
            raise ValidationError("Hysteresis must fit inside the approved range.")
        if any(not 1 <= data[key] <= 86400 for key in ["sustained_sec", "recovery_sec"]):
            raise ValidationError("Durations must be 1..86400 seconds.")
        return data

    class Meta:
        """Server assigns scope, version number and actor; no threshold defaults are supplied."""

        model = models.RuleVersion
        fields = [
            "id",
            "ruleset",
            "version",
            "lower_bound",
            "upper_bound",
            "hysteresis",
            "sustained_sec",
            "recovery_sec",
            "sop_reference",
            "created_at",
            "stage",
            "latest_backtest",
            "approval",
        ]
        read_only_fields = ["id", "version", "created_at", "stage", "latest_backtest", "approval"]
        validators = []


class RuleView(TelemetryView):
    """Resolve exact site access before rule IDs; authoring permits QA or site managers."""

    def author_site(self):
        """Check live independent roles; platform metadata permissions never grant rule access."""
        site = self.site()
        if (
            not sites_for(self.request.user, site.organisation_id, [Role.SITE_ADMIN, Role.QA])
            .filter(pk=site.pk)
            .exists()
        ):
            raise PermissionDenied()
        step_up(self.request)
        return site

    def version(self, site, identifier):
        """Look up only exact-site versions; absent and foreign UUIDs are indistinguishable."""
        item = models.RuleVersion.objects.filter(
            pk=identifier, site=site, organisation=site.organisation
        ).first()
        if not item:
            raise NotFound()
        return item


class FamiliesView(RuleView):
    """One rule family per zone; unsupported rapid-change adapters have no activation path."""

    serializer_class = FamilySerializer

    @extend_schema(responses=FamilySerializer(many=True))
    def get(self, request, org_id, site_id):
        """Return the permitted site's rule families."""
        return self.listing(models.RuleSet.objects.filter(site=self.site()).order_by("id"))

    def post(self, request, org_id, site_id):
        """Create an explicit temperature family without generating any food-safety thresholds."""
        site = self.author_site()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not Zone.objects.filter(
            pk=serializer.validated_data["zone_id"], site=site, organisation=site.organisation
        ).exists():
            raise NotFound()
        with transaction.atomic():
            Site.objects.select_for_update().get(pk=site.pk)
            item = serializer.save(organisation=site.organisation, site=site)
            record(
                "rule.family_created",
                actor=request.user,
                organisation=site.organisation,
                site=site,
                subject=item.pk,
            )
        return Response(serializer.data, status=201)


class VersionsView(RuleView):
    """Append-only draft creation; no PATCH/DELETE route can silently alter approved behavior."""

    serializer_class = VersionSerializer

    @extend_schema(responses=VersionSerializer(many=True))
    def get(self, request, org_id, site_id):
        """List preserved versions with current lifecycle derived from separate evidence."""
        return self.listing(
            models.RuleVersion.objects.filter(site=self.site()).order_by("-created_at", "id")
        )

    def post(self, request, org_id, site_id):
        """Serialize version numbering with inventory scope under the site lock."""
        site = self.author_site()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            Site.objects.select_for_update().get(pk=site.pk)
            family = models.RuleSet.objects.filter(
                pk=serializer.validated_data["ruleset_id"],
                site=site,
                organisation=site.organisation,
            ).first()
            if not family:
                raise NotFound()
            latest = models.RuleVersion.objects.filter(ruleset=family).order_by("-version").first()
            item = serializer.save(
                organisation=site.organisation,
                site=site,
                version=latest.version + 1 if latest else 1,
                created_by=request.user,
            )
            record(
                "rule.version_created",
                actor=request.user,
                organisation=site.organisation,
                site=site,
                subject=item.pk,
            )
        return Response(serializer.data, status=201)


class BacktestInput(StrictInputMixin, TimeWindow):
    """Explicit UTC-offset range; no arbitrary query/code expression is accepted."""


class BacktestSerializer(serializers.ModelSerializer):
    """Preserved preview includes input hash, excluded count and deterministic transition times."""

    class Meta:
        """All simulation output is read-only and marked synthetic."""

        model = models.RuleBacktest
        fields = ["id", "version", "start", "end", "result", "input_hash", "created_at"]
        read_only_fields = fields


class BacktestView(RuleView):
    """Read/run bounded previews; user-supplied clocks never affect live incident processing."""

    serializer_class = BacktestSerializer

    @extend_schema(responses=BacktestSerializer(many=True))
    def get(self, request, org_id, site_id, version_id):
        """Scope both version and its evidence before pagination."""
        version = self.version(self.site(), version_id)
        return self.listing(
            models.RuleBacktest.objects.filter(version=version).order_by("-created_at", "id")
        )

    @extend_schema(request=BacktestInput, responses={201: BacktestSerializer})
    def post(self, request, org_id, site_id, version_id):
        """Test an immutable version against qualified history and record the simulation."""
        site = self.author_site()
        version = self.version(site, version_id)
        data = inputs(BacktestInput, request)
        result = services.backtest(version, request.user, data["start"], data["end"])
        record(
            "rule.backtested",
            actor=request.user,
            organisation=site.organisation,
            site=site,
            subject=result.pk,
        )
        return Response(self.get_serializer(result).data, status=201)


class ApprovalInput(StrictInputMixin, serializers.Serializer):
    """QA chooses the exact reviewed simulation, not an arbitrary approval flag."""

    backtest = serializers.UUIDField()


class ApprovalSerializer(serializers.ModelSerializer):
    """Immutable approval evidence binds a version and test to current qualification/timing."""

    class Meta:
        """No caller can set synthetic provenance, reviewer or approval timestamp."""

        model = models.RuleApproval
        fields = [
            "id",
            "version",
            "backtest",
            "approved_by",
            "approved_at",
            "snapshot_hash",
            "synthetic",
        ]
        read_only_fields = fields


class ApprovalView(RuleView):
    """Require actual QA role plus fresh MFA, independently from ownership/administration."""

    serializer_class = ApprovalSerializer

    @extend_schema(request=ApprovalInput, responses={201: ApprovalSerializer})
    def post(self, request, org_id, site_id, version_id):
        """Reject owner-only approval and stale/empty/foreign backtests."""
        site = self.site()
        require_qa(request.user, site)
        step_up(request)
        version = self.version(site, version_id)
        data = inputs(ApprovalInput, request)
        with transaction.atomic():
            Site.objects.select_for_update().get(pk=site.pk)
            approval = services.approve(version, data["backtest"], request.user)
        return Response(self.get_serializer(approval).data, status=201)


class ActivationSerializer(serializers.ModelSerializer):
    """An effective boundary does not approve actual monitored-site go-live."""

    class Meta:
        """Server selects activation time under serialized family lock."""

        model = models.RuleActivation
        fields = ["id", "approval", "effective_at"]
        read_only_fields = fields


class ActivateView(RuleView):
    """Activate only a current approval; newer boundaries supersede old versions without overlap."""

    serializer_class = ActivationSerializer

    @extend_schema(request=None)
    def post(self, request, org_id, site_id, version_id):
        """Require management and fresh MFA; an unapproved version never governs evaluation."""
        site = self.site(True)
        step_up(request)
        version = self.version(site, version_id)
        approval = models.RuleApproval.objects.filter(version=version).first()
        if not approval:
            raise ValidationError("Explicit QA approval required.")
        return Response(
            self.get_serializer(services.activate(approval, request.user)).data, status=201
        )


class SuppressionSerializer(StrictInputMixin, serializers.ModelSerializer):
    """Explicit maintenance expiry/reason; null sensor applies to the exact site only."""

    sensor = serializers.UUIDField(source="sensor_id", allow_null=True, required=False)

    def validate(self, data):
        """Bound maintenance to 24 hours and require a future end; no indefinite hidden mute."""
        window = TimeWindow(data={key: self.initial_data[key] for key in ["start", "end"]})
        window.is_valid(raise_exception=True)
        if (
            not timedelta(0) < data["end"] - data["start"] <= timedelta(hours=24)
            or data["end"] <= timezone.now()
        ):
            raise ValidationError("Use an unexpired positive window of at most 24 hours.")
        return data

    class Meta:
        """Scope/actor/time are server-derived; existing windows are append-only."""

        model = models.SuppressionWindow
        fields = ["id", "sensor", "start", "end", "reason", "created_by"]
        read_only_fields = ["id", "created_by"]


class SuppressionView(RuleView):
    """Visible maintenance never removes readings or incident evidence."""

    serializer_class = SuppressionSerializer

    @extend_schema(responses=SuppressionSerializer(many=True))
    def get(self, request, org_id, site_id):
        """Preserve expired windows for incident reconstruction."""
        return self.listing(
            models.SuppressionWindow.objects.filter(site=self.site()).order_by("-start", "id")
        )

    def post(self, request, org_id, site_id):
        """Require site manager or QA and recent MFA for any maintenance window."""
        site = self.author_site()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sensor = serializer.validated_data.get("sensor_id")
        if (
            sensor
            and not Sensor.objects.filter(
                pk=sensor, site=site, organisation=site.organisation
            ).exists()
        ):
            raise NotFound()
        item = serializer.save(organisation=site.organisation, site=site, created_by=request.user)
        record(
            "rule.maintenance_created",
            actor=request.user,
            organisation=site.organisation,
            site=site,
            subject=item.pk,
            after=serializer.data,
        )
        return Response(serializer.data, status=201)
