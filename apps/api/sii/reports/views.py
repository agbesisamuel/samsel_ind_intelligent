"""Exact-site report admission, status, retry and authenticated expiring downloads."""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from sii.accounts.views import inputs
from sii.assets.models import Zone
from sii.incidents.views import download_response
from sii.telemetry.contracts import TimeWindow
from sii.telemetry.views import TelemetryView
from sii.tenants.serializers import StrictInputMixin

from . import services
from .models import ReportJob


class ReportInput(StrictInputMixin, TimeWindow):
    """Explicit half-open offset timestamps with a bounded raw-evidence scope."""

    zone = serializers.UUIDField(required=False)
    format = serializers.ChoiceField(choices=["pdf", "csv"])
    locale = serializers.ChoiceField(choices=["en", "da"])


class ReportSerializer(serializers.ModelSerializer):
    """Expose lifecycle/checksum without private object keys or source snapshot bodies."""

    class Meta:
        """Immutable request and safe worker state only."""

        model = ReportJob
        fields = [
            "id",
            "zone",
            "start",
            "end",
            "format",
            "locale",
            "requested_at",
            "expires_at",
            "status",
            "attempts",
            "error_code",
            "checksum",
            "size",
        ]
        read_only_fields = fields


class ReportsView(TelemetryView):
    """Scope/role checks precede listing counts and object lookup."""

    serializer_class = ReportSerializer

    def report(self, identifier):
        """Return identical missing/foreign errors after current export authorization."""
        site = self.site()
        services.require_export(self.request.user, site)
        job = ReportJob.objects.filter(site=site, pk=identifier).first()
        if not job:
            raise NotFound()
        return job

    @extend_schema(responses=ReportSerializer(many=True))
    def get(self, request, org_id, site_id):
        """List bounded report lifecycle metadata in the authorized site."""
        site = self.site()
        services.require_export(request.user, site)
        return self.listing(ReportJob.objects.filter(site=site).order_by("-requested_at", "id"))

    @extend_schema(request=ReportInput, responses={202: ReportSerializer})
    def post(self, request, org_id, site_id):
        """Validate scope before freezing the intent and return immediately for polling."""
        site = self.site()
        services.require_export(request.user, site)
        data = inputs(ReportInput, request)
        zone_id = data.pop("zone", None)
        zone = Zone.objects.filter(site=site, pk=zone_id).first() if zone_id else None
        if zone_id and not zone:
            raise NotFound()
        return Response(
            self.get_serializer(services.request_report(request.user, site, data, zone)).data,
            status=202,
        )


class RetryView(ReportsView):
    """Explicit retry of the original report; never change its source cutoff."""

    @extend_schema(request=None, responses=ReportSerializer)
    def post(self, request, org_id, site_id, job_id):
        """Recheck current export privileges before queuing a bounded retry."""
        return Response(self.get_serializer(services.retry(self.report(job_id), request.user)).data)

    http_method_names = ["post", "options"]


class GrantSerializer(serializers.Serializer):
    """An identity-bound handle is not an anonymous bearer credential."""

    id = serializers.UUIDField()
    expires_at = serializers.DateTimeField()


class GrantView(ReportsView):
    """Issue a short-lived handle without exposing storage endpoints."""

    @extend_schema(request=None, responses=GrantSerializer)
    def post(self, request, org_id, site_id, job_id):
        """Only ready unexpired artifacts can receive a download handle."""
        return Response(GrantSerializer(services.grant(self.report(job_id), request.user)).data)

    http_method_names = ["post", "options"]


class DownloadView(ReportsView):
    """Current authorization plus single-use grant and ciphertext integrity protect each read."""

    @extend_schema(responses={(200, "application/octet-stream"): bytes})
    def get(self, request, org_id, site_id, job_id, grant_id):
        """Return a forced attachment, never an anonymous S3 redirect."""
        job = self.report(job_id)
        body = services.download(job, request.user, grant_id)
        return download_response(
            body,
            f"report-{job.pk}.{job.format}",
            "application/pdf" if job.format == "pdf" else "text/csv",
        )

    http_method_names = ["get", "options"]
