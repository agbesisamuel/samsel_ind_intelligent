"""Scoped freshness dashboards and bounded UTC time-series reads with explicit gap provenance."""

from datetime import UTC, timedelta

from django.db import connection, transaction
from django.db.models import Avg, Count, Max, Min, Q
from django.db.models.functions import TruncHour
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from sii.accounts.security import step_up
from sii.accounts.views import inputs
from sii.assets.models import Sensor
from sii.assets.services import require_qa
from sii.audit.services import record
from sii.telemetry.contracts import ReadingWindow
from sii.telemetry.models import Reading
from sii.telemetry.views import ReadingSerializer, TelemetryView
from sii.tenants.models import Site
from sii.tenants.serializers import StrictInputMixin

from .models import FreshnessPolicy, SensorState
from .services import visible_state


class PolicyInput(StrictInputMixin, serializers.Serializer):
    """Explicit bounded timing, approved independently from customer alarm thresholds."""

    sensor_grace_sec = serializers.IntegerField(min_value=0, max_value=86400)
    gateway_timeout_sec = serializers.IntegerField(min_value=10, max_value=86400)
    sop_reference = serializers.CharField(max_length=240)


class PolicySerializer(serializers.ModelSerializer):
    """Immutable policy evidence includes the exact cadence snapshot and approving QA actor."""

    class Meta:
        """Read-only evidence; changes always produce a new approved policy version."""

        model = FreshnessPolicy
        fields = [
            "id",
            "sensor_grace_sec",
            "gateway_timeout_sec",
            "sop_reference",
            "intervals",
            "approved_by",
            "approved_at",
        ]
        read_only_fields = fields


class PolicyView(TelemetryView):
    """Any scoped reader can inspect policy; only explicit site QA can approve it."""

    serializer_class = PolicySerializer

    @extend_schema(responses=PolicySerializer(many=True))
    def get(self, request, org_id, site_id):
        """Return preserved approvals without replacing previous evidence."""
        return self.listing(
            FreshnessPolicy.objects.filter(site=self.site()).order_by("-approved_at", "id")
        )

    @extend_schema(request=PolicyInput, responses={201: PolicySerializer})
    def post(self, request, org_id, site_id):
        """Snapshot cadence under the same site lock as inventory writes after recent QA MFA."""
        site = self.site()
        require_qa(request.user, site)
        step_up(request)
        data = inputs(PolicyInput, request)
        with transaction.atomic():
            Site.objects.select_for_update().get(pk=site.pk)
            intervals = {
                str(s.pk): s.expected_interval_sec
                for s in Sensor.objects.filter(site=site).exclude(state="retired")
            }
            if not intervals:
                raise ValidationError("Register sensors before timing approval.")
            policy = FreshnessPolicy.objects.create(
                organisation=site.organisation,
                site=site,
                intervals=intervals,
                approved_by=request.user,
                **data,
            )
            record(
                "freshness.policy_approved",
                actor=request.user,
                organisation=site.organisation,
                site=site,
                subject=policy.pk,
                after=data,
            )
        return Response(PolicySerializer(policy).data, status=201)


class StateSerializer(serializers.ModelSerializer):
    """No-data value is null; current status is invalidated if the watcher heartbeat ages out."""

    name = serializers.CharField(source="sensor.name")
    zone = serializers.CharField(source="sensor.zone.name")
    gateway = serializers.UUIDField(source="sensor.gateway_id")
    current_status = serializers.SerializerMethodField()
    gateway_status = serializers.SerializerMethodField()
    reading = ReadingSerializer(allow_null=True)

    @extend_schema_field(serializers.CharField())
    def get_current_status(self, projection):
        """Prevent stale cached freshness from becoming a false healthy API response."""
        return visible_state(projection)

    @extend_schema_field(serializers.CharField())
    def get_gateway_status(self, projection):
        """Do not show cached gateway online status when its watcher is delayed."""
        return (
            "unknown"
            if visible_state(projection) == "watcher_delayed"
            else projection.gateway_status
        )

    class Meta:
        """Only normalized observation and quality evidence are exposed."""

        model = SensorState
        fields = [
            "sensor",
            "name",
            "zone",
            "gateway",
            "reading",
            "current_status",
            "gateway_status",
            "evaluated_at",
            "last_received_at",
            "quality",
        ]
        read_only_fields = fields


class DashboardView(TelemetryView):
    """Paginated exact-site projections; absent watcher state never implies healthy data."""

    serializer_class = StateSerializer

    @extend_schema(responses=StateSerializer(many=True))
    def get(self, request, org_id, site_id):
        """Scope before joining sensor names/reading history, avoiding foreign metadata leakage."""
        site = self.site()
        return self.listing(
            SensorState.objects.filter(site=site, organisation=site.organisation)
            .select_related("sensor__zone", "reading")
            .order_by("sensor__name", "id")
        )


class SeriesPoint(serializers.Serializer):
    """Hour buckets carry counts, imports and flags; absent buckets are explicit null values."""

    start = serializers.DateTimeField()
    count = serializers.IntegerField()
    imported = serializers.IntegerField()
    flagged = serializers.IntegerField()
    minimum = serializers.DecimalField(max_digits=12, decimal_places=4, allow_null=True)
    maximum = serializers.DecimalField(max_digits=12, decimal_places=4, allow_null=True)
    average = serializers.DecimalField(max_digits=12, decimal_places=4, allow_null=True)


class SeriesResult(serializers.Serializer):
    """Bounded hourly aggregate response, never an unlabeled replacement for raw evidence."""

    timezone = serializers.CharField()
    unit = serializers.CharField()
    provenance = serializers.CharField()
    expected_interval_sec = serializers.IntegerField()
    points = SeriesPoint(many=True)


class SeriesView(TelemetryView):
    """Aggregate in UTC so a DST-fold hour cannot merge with its repeated local hour."""

    serializer_class = SeriesResult

    @extend_schema(parameters=[ReadingWindow])
    def get(self, request, org_id, site_id):
        """Return raw-derived min/max/mean and explicit empty buckets within the selected window."""
        site = self.site()
        query = ReadingWindow(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data
        sensor = Sensor.objects.filter(
            pk=data["sensor"], site=site, organisation=site.organisation
        ).first()
        if not sensor:
            raise NotFound()
        rows = (
            Reading.objects.filter(
                sensor=sensor,
                site=site,
                organisation=site.organisation,
                observed_at__gte=data["start"],
                observed_at__lt=data["end"],
            )
            .annotate(start=TruncHour("observed_at", tzinfo=UTC))
            .values("start")
            .annotate(
                count=Count("id"),
                imported=Count("id", filter=Q(source="manual_import")),
                flagged=Count("id", filter=~Q(quality=["synthetic"])),
                minimum=Min("value"),
                maximum=Max("value"),
                average=Avg("value"),
            )
        )
        indexed = {r["start"]: r for r in rows}
        current = data["start"].astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        points = []
        while current < data["end"]:
            points.append(
                indexed.get(
                    current,
                    {
                        "start": current,
                        "count": 0,
                        "imported": 0,
                        "flagged": 0,
                        "minimum": None,
                        "maximum": None,
                        "average": None,
                    },
                )
            )
            current += timedelta(hours=1)
        return Response(
            SeriesResult(
                {
                    "timezone": site.timezone,
                    "unit": sensor.unit,
                    "provenance": "hourly raw-row aggregates; partial boundary buckets",
                    "expected_interval_sec": sensor.expected_interval_sec,
                    "points": points,
                }
            ).data
        )


class LatencyResult(serializers.Serializer):
    """Processing latency excludes device observation/backfill age and reports its sample size."""

    p95_processing_seconds = serializers.FloatField(allow_null=True)
    samples = serializers.IntegerField()


class LatencyView(TelemetryView):
    """Exact database percentile over the last 24 hours, scoped before aggregation."""

    serializer_class = LatencyResult

    def get(self, request, org_id, site_id):
        """Measure receipt-to-processing latency; ingress metrics separately report pending work."""
        site = self.site()
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT percentile_cont(0.95) WITHIN GROUP
                (ORDER BY extract(epoch FROM (o.processed_at-r.received_at))), count(*)
                FROM telemetry_processingoutbox o JOIN telemetry_reading r ON r.id=o.reading_id
                WHERE r.organisation_id=%s AND r.site_id=%s AND r.received_at >= %s
                AND o.processed_at IS NOT NULL""",
                [site.organisation_id, site.pk, timezone.now() - timedelta(days=1)],
            )
            percentile, count = cursor.fetchone()
        return Response({"p95_processing_seconds": percentile, "samples": count})
