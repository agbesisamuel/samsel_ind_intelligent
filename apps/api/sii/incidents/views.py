"""Scoped incident response, immutable evidence and authorized activity exports."""

import io
import json

from django.db.models import Q
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ParseError, PermissionDenied
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from sii.accounts.models import CustomUser
from sii.accounts.security import step_up
from sii.accounts.views import inputs
from sii.audit.services import record
from sii.common import storage
from sii.notifications.models import Notification
from sii.notifications.views import CandidateSerializer, NotificationSerializer
from sii.telemetry.views import TelemetryView
from sii.tenants.access import sites_for
from sii.tenants.models import RoleAssignment
from sii.tenants.serializers import StrictInputMixin

from . import attachments, workflow
from .models import EvidenceAttachment, Incident, IncidentEvent


class IncidentSerializer(serializers.ModelSerializer):
    """Distinguish human status and observed recovery; do not infer closure or safety."""

    assigned_label = serializers.EmailField(
        source="assigned_to.email", read_only=True, allow_null=True
    )

    class Meta:
        """Read-only episode identity and provenance."""

        model = Incident
        fields = [
            "id",
            "sensor",
            "gateway",
            "rule_version",
            "kind",
            "status",
            "opened_at",
            "recovered_at",
            "acknowledged_at",
            "assigned_to",
            "closed_at",
            "revision",
            "assigned_label",
            "synthetic",
        ]
        read_only_fields = fields


class EventSerializer(serializers.ModelSerializer):
    """Immutable timeline retains reference IDs and maintenance evidence."""

    class Meta:
        """Preserved chronology ordered by event time and stable UUID."""

        model = IncidentEvent
        fields = ["id", "kind", "occurred_at", "actor", "evidence", "correlation_id"]
        read_only_fields = fields


class IncidentsView(TelemetryView):
    """List exact-site incidents, retaining unresolved recovery and synthetic markers."""

    serializer_class = IncidentSerializer

    @extend_schema(responses=IncidentSerializer(many=True))
    def get(self, request, org_id, site_id):
        """Scope before filters, ordering and pagination."""
        query = Incident.objects.filter(site=self.site())
        if request.query_params.get("status"):
            query = query.filter(status=request.query_params["status"])
        if request.query_params.get("kind"):
            query = query.filter(kind=request.query_params["kind"])
        return self.listing(query.order_by("-opened_at", "id"))


class IncidentDetail(TelemetryView):
    """Retrieve an exact-site episode; foreign and absent identifiers both return 404."""

    serializer_class = IncidentSerializer

    def get(self, request, org_id, site_id, incident_id):
        """Resolve the site before the requested incident."""
        item = Incident.objects.filter(site=self.site(), pk=incident_id).first()
        if not item:
            raise NotFound()
        return Response(self.get_serializer(item).data)


class EventsView(TelemetryView):
    """Read preserved chronology without mutation endpoints."""

    serializer_class = EventSerializer

    @extend_schema(responses=EventSerializer(many=True))
    def get(self, request, org_id, site_id, incident_id):
        """Enforce both nested parent and exact site before disclosing event evidence."""
        incident = Incident.objects.filter(site=self.site(), pk=incident_id).first()
        if not incident:
            raise NotFound()
        return self.listing(
            IncidentEvent.objects.filter(incident=incident).order_by("occurred_at", "id")
        )


class IncidentScopedView(TelemetryView):
    """Resolve the exact site before loading any incident or subordinate evidence identifier."""

    def incident(self, identifier):
        """Make foreign and absent incidents indistinguishable."""
        item = Incident.objects.filter(site=self.site(), pk=identifier).first()
        if not item:
            raise NotFound()
        return item


class CommandInput(StrictInputMixin, serializers.Serializer):
    """Explicit human commands with concurrency revision and caller-generated replay identifier."""

    action = serializers.ChoiceField(
        choices=[
            "acknowledge",
            "assign",
            "investigate",
            "corrective_action",
            "qa_review",
            "close",
            "amend",
        ]
    )
    text = serializers.CharField(min_length=8, max_length=4000)
    assignee = serializers.UUIDField(required=False)
    revision = serializers.IntegerField(min_value=0)
    request_id = serializers.UUIDField()

    def validate(self, data):
        """Require assignment identity only for assignment, avoiding ambiguous commands."""
        if (data["action"] == "assign") != ("assignee" in data):
            raise serializers.ValidationError("Assignment requires one assignee.")
        return data


class AssigneesView(IncidentScopedView):
    """Offer eligible responders only to users authorized to assign incident work."""

    serializer_class = CandidateSerializer

    @extend_schema(responses=CandidateSerializer(many=True))
    def get(self, request, org_id, site_id, incident_id):
        """Resolve exact incident scope and operational roles before listing identities."""
        item = self.incident(incident_id)
        workflow.require_responder(request.user, item.site, managers=True)
        grants = RoleAssignment.objects.filter(
            organisation=item.organisation, membership__active=True
        ).filter(Q(role="owner") | Q(site=item.site, role__in=workflow.RESPONDERS))
        return self.listing(
            CustomUser.objects.filter(
                pk__in=grants.values("membership__user_id"),
                is_active=True,
                verified_at__isnull=False,
            ).order_by("email")
        )


class CommandView(IncidentScopedView):
    """Perform validated transitions; recent MFA is mandatory for independent QA review/closure."""

    serializer_class = IncidentSerializer

    @extend_schema(request=CommandInput)
    def post(self, request, org_id, site_id, incident_id):
        """Authorize live roles in the service and return the new revision for further actions."""
        item = self.incident(incident_id)
        data = inputs(CommandInput, request)
        if data["action"] in {"qa_review", "close"}:
            step_up(request)
        return Response(self.get_serializer(workflow.transition(item, request.user, data)).data)


class AttachmentSerializer(serializers.ModelSerializer):
    """Immutable attachment metadata excludes private storage keys and encryption material."""

    class Meta:
        """Downloads resolve server-owned object identity after authorization."""

        model = EvidenceAttachment
        fields = ["id", "label", "checksum", "size", "uploaded_by", "uploaded_at"]
        read_only_fields = fields


class AttachmentInput(StrictInputMixin, serializers.Serializer):
    """Bound labels/revision and delegate content validation to the plain-text-only service."""

    file = serializers.FileField(max_length=120)
    label = serializers.CharField(min_length=3, max_length=120)
    revision = serializers.IntegerField(min_value=0)


class BoundedMultipart(MultiPartParser):
    """Cap multipart bytes before Django's file handlers allocate temporary files."""

    def parse(self, stream, media_type=None, parser_context=None):
        """Reject oversized/chunked requests before parsing any user-supplied filename/content."""
        raw = stream.read(131073)
        if len(raw) > 131072:
            raise ParseError("Upload request exceeds 128 KiB.")
        return super().parse(io.BytesIO(raw), media_type, parser_context)


class AttachmentsView(IncidentScopedView):
    """Read/upload exact-incident constrained evidence; no arbitrary remote URL fetch exists."""

    serializer_class = AttachmentSerializer
    parser_classes = [BoundedMultipart]

    @extend_schema(responses=AttachmentSerializer(many=True))
    def get(self, request, org_id, site_id, incident_id):
        """List immutable metadata in upload order."""
        return self.listing(
            EvidenceAttachment.objects.filter(incident=self.incident(incident_id)).order_by(
                "uploaded_at", "id"
            )
        )

    @extend_schema(request=AttachmentInput, responses={201: AttachmentSerializer})
    def post(self, request, org_id, site_id, incident_id):
        """Validate UTF-8 text and current incident revision before encrypted storage."""
        item = self.incident(incident_id)
        data = inputs(AttachmentInput, request)
        result = attachments.attach(
            item, request.user, data["file"], data["label"], data["revision"]
        )
        return Response(self.get_serializer(result).data, status=201)


def download_response(body, filename, content_type):
    """Force attachment and deny active rendering/cache; filenames are supplied by server code."""
    response = HttpResponse(body, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "sandbox; default-src 'none'"
    response["Cache-Control"] = "no-store"
    return response


class AttachmentDownload(IncidentScopedView):
    """Authorize first, then authenticate/decrypt one exact-scope artifact and audit access."""

    @extend_schema(responses={(200, "text/plain"): bytes})
    def get(self, request, org_id, site_id, incident_id, attachment_id):
        """Never redirect to storage or disclose a reusable bearer URL."""
        incident = self.incident(incident_id)
        item = EvidenceAttachment.objects.filter(incident=incident, pk=attachment_id).first()
        if not item:
            raise NotFound()
        body = storage.get(item.organisation_id, item.site_id, item.pk, item.checksum)
        record(
            "evidence.downloaded",
            actor=request.user,
            organisation=item.organisation,
            site=item.site,
            subject=item.pk,
        )
        return download_response(body, f"evidence-{item.pk}.txt", "text/plain; charset=utf-8")


class IncidentNotifications(IncidentScopedView):
    """Read provider attempts alongside, never in place of, human acknowledgement events."""

    serializer_class = NotificationSerializer

    @extend_schema(responses=NotificationSerializer(many=True))
    def get(self, request, org_id, site_id, incident_id):
        """Resolve the incident before any delivery query."""
        item = self.incident(incident_id)
        return self.listing(
            Notification.objects.filter(event__incident=item).order_by("created_at", "id")
        )


class ActivityExport(IncidentScopedView):
    """Download bounded incident chronology with scope/provenance and an access audit record."""

    @extend_schema(responses={(200, "application/json"): dict})
    def get(self, request, org_id, site_id, incident_id):
        """Restrict exports to operational managers/QA/auditors; never modify source evidence."""
        item = self.incident(incident_id)
        if (
            not sites_for(
                request.user, item.organisation_id, ["site_admin", "qa", "operations", "auditor"]
            )
            .filter(pk=item.site_id)
            .exists()
        ):
            raise PermissionDenied()
        events = item.events.order_by("occurred_at", "id")
        if events.count() > 10000:
            raise serializers.ValidationError("Use a bounded asynchronous report for this history.")
        body = json.dumps(
            {
                "schema_version": 1,
                "synthetic": True,
                "organisation": str(item.organisation_id),
                "site": str(item.site_id),
                "incident": IncidentSerializer(item).data,
                "events": EventSerializer(events, many=True).data,
                "attachments": AttachmentSerializer(
                    EvidenceAttachment.objects.filter(incident=item), many=True
                ).data,
            },
            default=str,
            sort_keys=True,
        ).encode()
        record(
            "incident.activity_exported",
            actor=request.user,
            organisation=item.organisation,
            site=item.site,
            subject=item.pk,
        )
        return download_response(body, f"incident-{item.pk}.json", "application/json")
