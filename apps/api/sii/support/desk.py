"""Scoped internal tickets and onboarding archive; no supplier sends or implicit staff access.

Support resolution never resolves a safety incident, modifies source evidence or
authorises hardware. Diagnostics support grants cannot read ticket bodies/files.
"""

from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from sii.accounts.views import inputs
from sii.adapters.models import PilotReview
from sii.adapters.views import AdapterStatusSerializer, readiness
from sii.assets.models import CommissioningAcceptance, SiteCommissioning
from sii.audit.services import record
from sii.reports.models import ReportJob, ReportSnapshot
from sii.reports.services import require_export
from sii.telemetry.views import TelemetryView
from sii.tenants.access import sites_for
from sii.tenants.models import Site
from sii.tenants.serializers import StrictInputMixin

from .models import SupportTicket, TicketEvent, TicketStatus


def tickets(user, site):
    """Operators see own requests; site QA/operations/admin/auditors review the scoped queue."""
    query = SupportTicket.objects.filter(organisation=site.organisation, site=site)
    if (
        not sites_for(user, site.organisation_id, ["site_admin", "qa", "operations", "auditor"])
        .filter(pk=site.pk)
        .exists()
    ):
        query = query.filter(reported_by=user)
    return query


def may_write(user, site):
    """Require an operational grant; an auditor-only assignment remains read-only."""
    if (
        not sites_for(user, site.organisation_id, ["site_admin", "qa", "operations", "operator"])
        .filter(pk=site.pk)
        .exists()
    ):
        raise PermissionDenied()


class TicketSerializer(serializers.ModelSerializer):
    """Preserved original content and current support state with server-owned provenance."""

    class Meta:
        """No direct edit/delete interface exists."""

        model = SupportTicket
        fields = [
            "id",
            "request_id",
            "subject",
            "body",
            "reported_by",
            "created_at",
            "status",
            "revision",
            "synthetic",
        ]
        read_only_fields = fields


class TicketInput(StrictInputMixin, serializers.Serializer):
    """Bounded request text/replay identity; no destination or tenant override is accepted."""

    request_id = serializers.UUIDField()
    subject = serializers.CharField(min_length=3, max_length=160)
    body = serializers.CharField(min_length=8, max_length=2000)


class TicketsView(TelemetryView):
    """Customer-local queue; platform flags or diagnostics sessions never bypass its scope."""

    serializer_class = TicketSerializer

    @extend_schema(responses=TicketSerializer(many=True))
    def get(self, request, org_id, site_id):
        """Apply site and operator ownership before paginating records or counts."""
        return self.listing(tickets(request.user, self.site()).order_by("-created_at", "-id"))

    @extend_schema(request=TicketInput, responses={201: TicketSerializer})
    @transaction.atomic
    def post(self, request, org_id, site_id):
        """Persist one original request; reject conflicting replay and overfull personal queues."""
        site = self.site()
        may_write(request.user, site)
        data = inputs(TicketInput, request)
        # Serialize admissions on the site; no commercial/gateway lock follows it.
        Site.objects.select_for_update().get(pk=site.pk)
        ticket = SupportTicket.objects.filter(site=site, request_id=data["request_id"]).first()
        if ticket:
            if ticket.reported_by_id != request.user.pk:
                raise NotFound()
            if ticket.subject != data["subject"] or ticket.body != data["body"]:
                raise ValidationError("Request identity already has different content")
        else:
            if (
                SupportTicket.objects.filter(site=site, reported_by=request.user)
                .exclude(status="resolved")
                .count()
                >= 20
            ):
                raise ValidationError("Review outstanding requests before opening more")
            ticket = SupportTicket.objects.create(
                organisation=site.organisation, site=site, reported_by=request.user, **data
            )
            TicketEvent.objects.create(
                organisation=site.organisation,
                site=site,
                ticket=ticket,
                actor=request.user,
                message=data["body"],
                status="open",
            )
            record(
                "support.ticket_created",
                actor=request.user,
                organisation=site.organisation,
                site=site,
                subject=ticket.pk,
            )
        return Response(self.get_serializer(ticket).data, status=201)


class TicketEventSerializer(serializers.ModelSerializer):
    """Immutable chronological response/status evidence."""

    class Meta:
        """Only the append endpoint can write a conversation event."""

        model = TicketEvent
        fields = ["id", "actor", "message", "status", "created_at"]
        read_only_fields = fields


class TicketNoteInput(StrictInputMixin, serializers.Serializer):
    """Bounded reply, current revision and explicit support state prevent lost updates."""

    revision = serializers.IntegerField(min_value=0)
    message = serializers.CharField(min_length=3, max_length=2000)
    status = serializers.ChoiceField(choices=TicketStatus.choices)


class TicketEventsView(TelemetryView):
    """Resolve each conversation through current ticket visibility before read or append."""

    serializer_class = TicketEventSerializer

    def ticket(self):
        """Keep foreign/absent/other-operator identifiers indistinguishable."""
        ticket = tickets(self.request.user, self.site()).filter(pk=self.kwargs["ticket_id"]).first()
        if not ticket:
            raise NotFound()
        return ticket

    @extend_schema(responses=TicketEventSerializer(many=True))
    def get(self, request, org_id, site_id, ticket_id):
        """Paginate only the authorised conversation."""
        return self.listing(
            TicketEvent.objects.filter(ticket=self.ticket()).order_by("created_at", "id")
        )

    @extend_schema(request=TicketNoteInput, responses={201: TicketEventSerializer})
    @transaction.atomic
    def post(self, request, org_id, site_id, ticket_id):
        """Append status/reply evidence while retaining original content and prior responses."""
        ticket = self.ticket()
        may_write(request.user, ticket.site)
        ticket = SupportTicket.objects.select_for_update().get(pk=ticket.pk)
        data = inputs(TicketNoteInput, request)
        if ticket.revision != data["revision"]:
            raise ValidationError("Support request changed; refresh before replying")
        event = TicketEvent.objects.create(
            organisation=ticket.organisation,
            site=ticket.site,
            ticket=ticket,
            actor=request.user,
            message=data["message"],
            status=data["status"],
        )
        ticket.status, ticket.revision = data["status"], ticket.revision + 1
        ticket.save(update_fields=["status", "revision"])
        record(
            "support.ticket_replied",
            actor=request.user,
            organisation=ticket.organisation,
            site=ticket.site,
            subject=ticket.pk,
            after={"status": ticket.status},
        )
        return Response(self.get_serializer(event).data, status=201)


class OperationalStatusSerializer(serializers.Serializer):
    """Site diagnostics and hard release gates without fabricated cloud/customer approvals."""

    site_status = AdapterStatusSerializer()
    production_eligible = serializers.BooleanField()
    blockers = serializers.ListField(child=serializers.CharField())
    onboarding_steps = serializers.ListField(child=serializers.CharField())


class OperationalStatus(TelemetryView):
    """Show only granted site diagnostics and preparation steps."""

    serializer_class = OperationalStatusSerializer

    def get(self, request, org_id, site_id):
        """No test, subscription state or synthetic acceptance can promote a real site."""
        snapshot = readiness(self.site())
        local_blockers = []
        if snapshot["unresolved_incidents"]:
            local_blockers.append("unresolved_incidents")
        if (
            snapshot["failed_notifications"]
            or snapshot["operational"]["exhausted_events"]
            or snapshot["operational"]["failed_reports"]
        ):
            local_blockers.append("failed_delivery_or_processing")
        return Response(
            {
                "site_status": snapshot,
                "production_eligible": False,
                "blockers": local_blockers
                + [
                    "authorised_hardware_site_missing",
                    "container_security_remediation",
                    "external_security_legal_privacy_review",
                    "cloud_paging_backup_and_site_drills",
                    "customer_qa_training_acceptance",
                    "finance_support_terms_review",
                ],
                "onboarding_steps": [
                    "scope_and_responsibilities",
                    "placement_and_calibration",
                    "qa_rules_and_cadence",
                    "routes_and_failure_drills",
                    "human_response_training",
                    "reviewed_acceptance_archive",
                ],
            }
        )


class ArtifactArchiveSerializer(serializers.Serializer):
    """Bounded source references/hashes; existing downloads keep their original authorization."""

    reports = serializers.ListField(child=serializers.JSONField())
    commissioning = serializers.ListField(child=serializers.JSONField())
    pilot_reviews = serializers.ListField(child=serializers.JSONField())
    packs = serializers.ListField(child=serializers.JSONField())
    limited_to_latest = serializers.IntegerField()


class ArtifactArchive(TelemetryView):
    """Only export-capable roles inspect report/acceptance provenance."""

    serializer_class = ArtifactArchiveSerializer

    def get(self, request, org_id, site_id):
        """Audit the latest 50 metadata records per type; never return public object URLs."""
        site = self.site()
        require_export(request.user, site)
        reports = list(
            ReportJob.objects.filter(site=site)
            .order_by("-requested_at")
            .values("id", "format", "status", "requested_at", "expires_at", "checksum")[:50]
        )
        hashes = dict(
            ReportSnapshot.objects.filter(job_id__in=[row["id"] for row in reports]).values_list(
                "job_id", "source_hash"
            )
        )
        for row in reports:
            row["source_hash"] = hashes.get(row["id"])
        result = {
            "reports": reports,
            "commissioning": list(
                CommissioningAcceptance.objects.filter(site=site)
                .order_by("-approved_at")
                .values("id", "approved_at", "evidence_hash", "synthetic")[:50]
            ),
            "pilot_reviews": list(
                PilotReview.objects.filter(site=site)
                .order_by("-recorded_at")
                .values("id", "recorded_at", "kind", "synthetic")[:50]
            ),
            "packs": list(
                SiteCommissioning.objects.filter(site=site)
                .order_by("-id")
                .values("id", "customer_approval_reference", "contingency_reference")[:50]
            ),
            "limited_to_latest": 50,
        }
        record(
            "onboarding.archive_read",
            actor=request.user,
            organisation=site.organisation,
            site=site,
            subject=site.pk,
        )
        return Response(result)
