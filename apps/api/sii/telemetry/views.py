"""Human administration of device secrets, ingress evidence and explicitly manual CSV imports."""

import csv
import io
import uuid
from urllib.error import URLError

from django.db.models import Count
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from sii.accounts.security import step_up
from sii.accounts.views import inputs
from sii.assets.models import Gateway, Sensor
from sii.assets.services import scoped_site
from sii.audit.services import record
from sii.tenants.serializers import StrictInputMixin
from sii.tenants.views import ScopedView

from .contracts import ReadingWindow
from .models import DeviceCredential, ProcessingOutbox, Reading, Rejection
from .security import provision, revoke
from .services import ingest


class CredentialSerializer(serializers.ModelSerializer):
    """Public lifecycle metadata deliberately excludes encrypted/clear secret material."""

    class Meta:
        """The only credential fields returned by list/revoke operations."""

        model = DeviceCredential
        fields = ["id", "gateway", "expires_at", "revoked_at", "provisioned"]
        read_only_fields = fields


class DeviceProvisionInput(StrictInputMixin, serializers.Serializer):
    """A new secret has a bounded lifetime; a second secret supports explicit overlap rotation."""

    gateway = serializers.UUIDField()
    days = serializers.IntegerField(min_value=1, max_value=90, default=30)


class IssuedCredential(CredentialSerializer):
    """Write response only: clear secret appears once and must never be placed in URLs."""

    secret = serializers.CharField()

    class Meta(CredentialSerializer.Meta):
        """Only provisioning includes the one-time secret."""

        fields = [*CredentialSerializer.Meta.fields, "secret"]


class TelemetryView(ScopedView):
    """Resolve current human grants on every request; device auth is never accepted."""

    def site(self, write=False):
        """Require exact site membership before metadata, counts or object lookup."""
        return scoped_site(self.request.user, self.kwargs["org_id"], self.kwargs["site_id"], write)


class CredentialsView(TelemetryView):
    """Managers can issue/list gateway credentials after recent privileged MFA."""

    serializer_class = CredentialSerializer

    @extend_schema(responses=CredentialSerializer(many=True))
    def get(self, request, org_id, site_id):
        """Credential metadata is management-only, even though no secrets are included."""
        return self.listing(DeviceCredential.objects.filter(site=self.site(True)).order_by("id"))

    @extend_schema(request=DeviceProvisionInput, responses={201: IssuedCredential})
    def post(self, request, org_id, site_id):
        """Broker failure leaves a visible pending credential and reveals no usable secret."""
        site = self.site(True)
        step_up(request)
        data = inputs(DeviceProvisionInput, request)
        gateway = Gateway.objects.filter(
            pk=data["gateway"], site=site, organisation=site.organisation
        ).first()
        if not gateway or gateway.state == "retired":
            raise NotFound()
        try:
            item, secret = provision(gateway, request.user, data["days"])
        except (URLError, TimeoutError):
            return Response(
                {"detail": "Broker unavailable; provisioning remains pending."}, status=503
            )
        return Response({**CredentialSerializer(item).data, "secret": secret}, status=201)


class RevokeView(TelemetryView):
    """Local revocation is durable even when broker disconnection cleanup needs retry."""

    serializer_class = CredentialSerializer

    @extend_schema(request=None)
    def post(self, request, org_id, site_id, credential_id):
        """Require current manager/step-up and scope before invalidating the credential."""
        site = self.site(True)
        step_up(request)
        item = DeviceCredential.objects.filter(
            pk=credential_id, site=site, organisation=site.organisation
        ).first()
        if not item:
            raise NotFound()
        try:
            revoke(item, request.user)
        except (URLError, TimeoutError):
            return Response(
                {"detail": "Revoked locally; broker cleanup must be retried."}, status=503
            )
        item.refresh_from_db()
        return Response(CredentialSerializer(item).data)


class ReadingSerializer(serializers.ModelSerializer):
    """Evidence read contract includes both clocks, provenance and qualification snapshot."""

    class Meta:
        """No raw payload in general read APIs; normalized fields preserve source meaning."""

        model = Reading
        fields = [
            "id",
            "sensor",
            "gateway",
            "event_id",
            "sequence",
            "observed_at",
            "received_at",
            "value",
            "unit",
            "source",
            "transport",
            "quality",
            "qualification",
            "payload_hash",
        ]
        read_only_fields = fields


class ReadingsView(TelemetryView):
    """Bounded ingress inspector, always constrained to URL site before pagination."""

    serializer_class = ReadingSerializer

    @extend_schema(parameters=[ReadingWindow], responses=ReadingSerializer(many=True))
    def get(self, request, org_id, site_id):
        """Return newest observations; late arrival does not reorder observation history."""
        site = self.site()
        items = Reading.objects.filter(site=site, organisation=site.organisation)
        if any(field in request.query_params for field in ["sensor", "start", "end"]):
            query = ReadingWindow(data=request.query_params)
            query.is_valid(raise_exception=True)
            data = query.validated_data
            if not Sensor.objects.filter(
                pk=data["sensor"], site=site, organisation=site.organisation
            ).exists():
                raise NotFound()
            items = items.filter(
                sensor_id=data["sensor"],
                observed_at__gte=data["start"],
                observed_at__lt=data["end"],
            )
        return self.listing(items.order_by("-observed_at", "id"))


class MetricsSerializer(serializers.Serializer):
    """Site-scoped operational counts, never customer safety or a public metrics leak."""

    accepted = serializers.IntegerField()
    pending = serializers.IntegerField()
    dead_lettered = serializers.IntegerField()
    rejected = serializers.DictField(child=serializers.IntegerField())


class MetricsView(TelemetryView):
    """Technical health separates persisted data, pending processing and rejection reasons."""

    serializer_class = MetricsSerializer

    def get(self, request, org_id, site_id):
        """All counts are scoped before aggregation."""
        site = self.site()
        pending = ProcessingOutbox.objects.filter(site=site, processed_at__isnull=True)
        return Response(
            {
                "accepted": Reading.objects.filter(site=site).count(),
                "pending": pending.count(),
                "dead_lettered": pending.filter(dead_lettered=True).count(),
                "rejected": dict(
                    Rejection.objects.filter(site=site)
                    .values_list("reason")
                    .annotate(n=Count("id"))
                ),
            }
        )


class CSVInput(StrictInputMixin, serializers.Serializer):
    """Bounded text CSV uses exact event headers, UTC offsets and explicit preview mode."""

    credential = serializers.UUIDField()
    csv = serializers.CharField(max_length=60000, trim_whitespace=False)
    preview = serializers.BooleanField(default=True)
    import_id = serializers.UUIDField(required=False)
    mapping = serializers.DictField(child=serializers.CharField(max_length=100), required=False)


class CSVResult(serializers.Serializer):
    """Per-row outcome identifies parsing/validation errors without silently dropping rows."""

    rows = serializers.ListField(child=serializers.DictField())
    source = serializers.CharField()


class CSVView(TelemetryView):
    """Import manual observations separately from device freshness; never qualify live feed."""

    serializer_class = CSVResult

    @extend_schema(request=CSVInput)
    def post(self, request, org_id, site_id):
        """Require manager step-up and exact credential scope for preview and commit alike."""
        site = self.site(True)
        step_up(request)
        data = inputs(CSVInput, request)
        credential = DeviceCredential.objects.filter(
            pk=data["credential"], site=site, organisation=site.organisation
        ).first()
        if not credential:
            raise NotFound()
        reader = csv.DictReader(io.StringIO(data["csv"]))
        fields = ["version", "event_id", "sensor_id", "sequence", "observed_at", "value", "unit"]
        mapping = data.get("mapping", {field: field for field in fields})
        required = {"sensor_id", "observed_at", "value", "unit"}
        if (
            not required <= set(mapping) <= set(fields)
            or not reader.fieldnames
            or len(set(reader.fieldnames)) != len(reader.fieldnames)
            or not set(mapping.values()) <= set(reader.fieldnames)
            or len(set(mapping.values())) != len(mapping)
        ):
            raise ValidationError(
                "Map unique existing columns to sensor_id, observed_at, value and unit."
            )
        if "event_id" not in mapping and "import_id" not in data:
            raise ValidationError("Provide a stable import_id when event_id is not mapped.")
        rows = list(reader)
        if not 1 <= len(rows) <= 100:
            raise ValidationError("Import requires 1–100 rows.")
        result = []
        for index, row in enumerate(rows, 2):
            if None in row or any(value is None for value in row.values()):
                result.append({"row": index, "status": "rejected", "reason": "column_count"})
                continue
            row = {field: row[column] for field, column in mapping.items()}
            row.setdefault("version", 1)
            row.setdefault("sequence", index - 2)
            if "event_id" not in row:
                row["event_id"] = str(uuid.uuid5(data["import_id"], str(index)))
            # Version/sequence are JSON integers in the shared wire contract.
            try:
                row["version"], row["sequence"] = int(row["version"]), int(row["sequence"])
            except (ValueError, TypeError):
                result.append({"row": index, "status": "rejected", "reason": "integer_format"})
                continue
            outcome = ingest(
                credential, row, "csv", source="manual_import", preview=data["preview"]
            )
            result.append({"row": index, **outcome})
        record(
            "telemetry.csv_preview" if data["preview"] else "telemetry.csv_import",
            actor=request.user,
            organisation=site.organisation,
            site=site,
        )
        return Response({"rows": result, "source": "manual_import"})
