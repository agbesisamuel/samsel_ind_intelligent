"""Exact-site software adapter readiness and immutable reviews; live use stays blocked."""

from collections import Counter

from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from sii.accounts.security import step_up
from sii.accounts.views import inputs
from sii.assets.models import Sensor
from sii.audit.services import record
from sii.incidents.models import Incident
from sii.monitoring.models import SensorState
from sii.monitoring.services import visible_state
from sii.notifications.models import Notification
from sii.reports.models import ReportJob
from sii.telemetry.models import ProcessingOutbox
from sii.telemetry.views import TelemetryView
from sii.tenants.access import sites_for
from sii.tenants.serializers import StrictInputMixin

from .models import PilotReview, ReviewKind
from .sdk import manifest


class AdapterStatusSerializer(serializers.Serializer):
    """Explicit technical preparation state; software evidence cannot assert customer acceptance."""

    status = serializers.CharField()
    live_enabled = serializers.BooleanField()
    profile = serializers.JSONField()
    sensors = serializers.IntegerField()
    unresolved_incidents = serializers.IntegerField()
    failed_notifications = serializers.IntegerField()
    sampled_at = serializers.DateTimeField()
    operational = serializers.JSONField()


def readiness(site):
    """Compute exact-site counts; an environment flag or synthetic review cannot enable live use."""
    sensors = Sensor.objects.filter(site=site).exclude(state="retired").count()
    statuses = Counter(
        visible_state(row)
        for row in SensorState.objects.filter(site=site)
        .exclude(sensor__state="retired")
        .select_related("sensor")
    )
    # Inventory can change between these read-only counts. Never show a negative
    # unknown count; the snapshot is diagnostic and cannot authorize commissioning.
    statuses["unknown"] += max(0, sensors - sum(statuses.values()))
    pending = ProcessingOutbox.objects.filter(site=site, processed_at__isnull=True)
    return {
        "status": "BLOCKED: no authorised hardware/site",
        "live_enabled": False,
        "profile": manifest(),
        "sensors": sensors,
        "unresolved_incidents": Incident.objects.filter(site=site).exclude(status="closed").count(),
        "failed_notifications": Notification.objects.filter(
            site=site, status__in=["dead", "uncertain"]
        ).count(),
        "sampled_at": timezone.now().isoformat(),
        "operational": {
            "sensor_states": dict(statuses),
            "pending_events": pending.count(),
            "exhausted_events": pending.filter(dead_lettered=True).count(),
            "queued_reports": ReportJob.objects.filter(
                site=site, status__in=["queued", "running"]
            ).count(),
            "failed_reports": ReportJob.objects.filter(site=site, status="failed").count(),
        },
    }


class AdapterReadiness(TelemetryView):
    """Read-only metadata never provisions hardware or grants access to platform staff."""

    serializer_class = AdapterStatusSerializer

    def get(self, request, org_id, site_id):
        """Resolve current scope before any counts or capabilities are disclosed."""
        return Response(readiness(self.site()))


class PilotReviewSerializer(serializers.ModelSerializer):
    """Return original actor/time/snapshot; reviews cannot be patched or removed."""

    class Meta:
        """Ownership, actor and synthetic provenance are always server controlled."""

        model = PilotReview
        fields = ["id", "kind", "note", "snapshot", "recorded_by", "recorded_at", "synthetic"]
        read_only_fields = fields


class PilotReviewInput(StrictInputMixin, serializers.Serializer):
    """Bounded local review text, with no live/approval/tenant override fields."""

    kind = serializers.ChoiceField(choices=ReviewKind.choices)
    note = serializers.CharField(min_length=8, max_length=1000)


class ReviewsView(TelemetryView):
    """Scoped synthetic health/feedback archive; auditors read and operational roles append."""

    serializer_class = PilotReviewSerializer

    @extend_schema(responses=PilotReviewSerializer(many=True))
    def get(self, request, org_id, site_id):
        """Paginate only the granted site's immutable observations."""
        return self.listing(
            PilotReview.objects.filter(site=self.site()).order_by("-recorded_at", "-id")
        )

    @extend_schema(request=PilotReviewInput, responses={201: PilotReviewSerializer})
    @transaction.atomic
    def post(self, request, org_id, site_id):
        """Require current operational authority and recent MFA before recording review evidence."""
        site = self.site()
        if (
            not sites_for(
                request.user, site.organisation_id, ["site_admin", "qa", "operations", "operator"]
            )
            .filter(pk=site.pk)
            .exists()
        ):
            raise NotFound()
        step_up(request)
        review = PilotReview.objects.create(
            organisation=site.organisation,
            site=site,
            recorded_by=request.user,
            snapshot=readiness(site),
            **inputs(PilotReviewInput, request),
        )
        record(
            "pilot.synthetic_review",
            actor=request.user,
            organisation=site.organisation,
            site=site,
            subject=review.pk,
            after={"kind": review.kind},
        )
        return Response(self.get_serializer(review).data, status=201)
