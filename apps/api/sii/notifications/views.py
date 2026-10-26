"""Exact-site notification consent, route drills and delivery-health APIs."""

from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from sii.accounts.models import CustomUser
from sii.accounts.security import step_up
from sii.accounts.views import inputs
from sii.audit.services import record
from sii.telemetry.views import TelemetryView
from sii.tenants.models import RoleAssignment, validate_timezone
from sii.tenants.serializers import StrictInputMixin

from . import models, services


class CandidateSerializer(serializers.ModelSerializer):
    """Manager-visible account identity already granted access to the exact site."""

    class Meta:
        """Expose recipient choices without membership or security internals."""

        model = CustomUser
        fields = ["id", "email"]
        read_only_fields = fields


class CandidatesView(TelemetryView):
    """Offer only active verified accounts with current grants to the URL site."""

    serializer_class = CandidateSerializer

    @extend_schema(responses=CandidateSerializer(many=True))
    def get(self, request, org_id, site_id):
        """Resolve recipient eligibility server-side so users select names rather than UUIDs."""
        site = self.site(True)
        grants = RoleAssignment.objects.filter(
            organisation=site.organisation, membership__active=True
        ).filter(Q(role="owner") | Q(site=site))
        return self.listing(
            CustomUser.objects.filter(
                pk__in=grants.values("membership__user_id"),
                is_active=True,
                verified_at__isnull=False,
            ).order_by("email")
        )


class ContactSerializer(serializers.ModelSerializer):
    """Expose proof state without tokens or token hashes."""

    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        """Consent identity and revocation state are read-only."""

        model = models.AlertContact
        fields = ["id", "user", "email", "verified_at", "disabled"]
        read_only_fields = fields


class ContactInput(StrictInputMixin, serializers.Serializer):
    """Invitation selects a currently granted account, never an arbitrary email address."""

    user = serializers.UUIDField()


class ContactProof(StrictInputMixin, serializers.Serializer):
    """Proof is a bounded secret supplied by the intended signed-in recipient."""

    token = serializers.CharField(min_length=32, max_length=100, write_only=True)


class ContactsView(TelemetryView):
    """List permitted contacts; managers may request opt-in, never manufacture verification."""

    serializer_class = ContactSerializer

    @extend_schema(responses=ContactSerializer(many=True))
    def get(self, request, org_id, site_id):
        """Scope before pagination; platform status provides no contact access."""
        return self.listing(models.AlertContact.objects.filter(site=self.site()).order_by("id"))

    @extend_schema(request=ContactInput, responses={201: ContactSerializer})
    def post(self, request, org_id, site_id):
        """Require recent MFA and management; the recipient must independently confirm."""
        site = self.site(True)
        step_up(request)
        data = inputs(ContactInput, request)
        user = CustomUser.objects.filter(
            pk=data["user"], is_active=True, verified_at__isnull=False
        ).first()
        if not user:
            raise NotFound()
        item = services.invite(site, user, request.user)
        return Response(self.get_serializer(item).data, status=201)


class ContactConfirm(TelemetryView):
    """Consume the recipient's single-use proof without granting route-management authority."""

    serializer_class = ContactSerializer

    @extend_schema(request=ContactProof)
    def post(self, request, org_id, site_id, contact_id):
        """Require exact site access and intended account; audit successful opt-in."""
        item = models.AlertContact.objects.filter(site=self.site(), pk=contact_id).first()
        if not item:
            raise NotFound()
        data = inputs(ContactProof, request)
        return Response(
            self.get_serializer(services.confirm(item, data["token"], request.user)).data
        )


class ContactDisable(TelemetryView):
    """Allow recipient opt-out or manager revocation; queued sends recheck consent."""

    @extend_schema(request=None, responses={204: None})
    def post(self, request, org_id, site_id, contact_id):
        """Revoke immediately without deleting proof history or referenced notification evidence."""
        site = self.site()
        item = models.AlertContact.objects.filter(site=site, pk=contact_id).first()
        if not item:
            raise NotFound()
        if item.user_id != request.user.pk:
            self.site(True)
            step_up(request)
        item.disabled = True
        item.save(update_fields=["disabled"])
        record(
            "notification.consent_revoked",
            actor=request.user,
            organisation=site.organisation,
            site=site,
            subject=item.pk,
        )
        return Response(status=204)


class RouteSerializer(StrictInputMixin, serializers.ModelSerializer):
    """Route input has explicit classification, severity, local shift and verified contacts."""

    contact = serializers.UUIDField(source="contact_id")
    contingency = serializers.UUIDField(source="contingency_id", allow_null=True, required=False)
    escalation_contact = serializers.UUIDField(write_only=True, required=False)
    delay_sec = serializers.IntegerField(
        min_value=30, max_value=86400, write_only=True, required=False
    )
    kinds = serializers.ListField(
        child=serializers.ChoiceField(
            choices=["too_warm", "too_cold", "invalid_reading", "sensor_no_data", "gateway_offline"]
        ),
        min_length=1,
        max_length=5,
    )
    severity = serializers.ChoiceField(choices=["info", "warning", "critical"])
    shift_start = serializers.IntegerField(min_value=0, max_value=1439)
    shift_end = serializers.IntegerField(min_value=0, max_value=1440)
    timezone = serializers.CharField(validators=[validate_timezone])

    def validate(self, data):
        """Reject ambiguous empty shifts and incomplete escalation configuration."""
        if data["shift_start"] == data["shift_end"]:
            raise ValidationError("Use 0..1440 for all-day coverage.")
        if ("escalation_contact" in data) != ("delay_sec" in data):
            raise ValidationError("Escalation requires contact and delay.")
        return data

    class Meta:
        """Route content is immutable after creation; activation is independently auditable."""

        model = models.AlertRoute
        fields = [
            "id",
            "name",
            "contact",
            "contingency",
            "escalation_contact",
            "delay_sec",
            "kinds",
            "severity",
            "timezone",
            "shift_start",
            "shift_end",
            "enabled",
            "created_at",
        ]
        read_only_fields = ["id", "enabled", "created_at"]


class RoutesView(TelemetryView):
    """Manage exact-site verified routes; multiple rows support multiple independent recipients."""

    serializer_class = RouteSerializer

    @extend_schema(responses=RouteSerializer(many=True))
    def get(self, request, org_id, site_id):
        """Return only site-scoped route configuration."""
        return self.listing(models.AlertRoute.objects.filter(site=self.site()).order_by("id"))

    def post(self, request, org_id, site_id):
        """Require recent MFA and current verified contact scope for every channel role."""
        site = self.site(True)
        step_up(request)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        secondary, delay = data.pop("escalation_contact", None), data.pop("delay_sec", None)
        for identifier in [data["contact_id"], data.get("contingency_id"), secondary]:
            if identifier:
                contact = models.AlertContact.objects.filter(site=site, pk=identifier).first()
                if not contact:
                    raise NotFound()
                if not services.eligible(contact):
                    raise ValidationError("Verified active opt-in required.")
        with transaction.atomic():
            item = models.AlertRoute.objects.create(
                organisation=site.organisation, site=site, created_by=request.user, **data
            )
            if secondary:
                models.EscalationPolicy.objects.create(
                    organisation=site.organisation,
                    site=site,
                    route=item,
                    contact_id=secondary,
                    delay_sec=delay,
                )
            record(
                "notification.route_created",
                actor=request.user,
                organisation=site.organisation,
                site=site,
                subject=item.pk,
            )
        return Response(self.get_serializer(item).data, status=201)


class EnabledInput(StrictInputMixin, serializers.Serializer):
    """Explicit reversible route switch; immutable recipients/configuration remain unchanged."""

    enabled = serializers.BooleanField()


class RouteEnabled(TelemetryView):
    """Audit enable/disable without editing historical routing content."""

    serializer_class = RouteSerializer

    @extend_schema(request=EnabledInput)
    def post(self, request, org_id, site_id, route_id):
        """Require management and step-up; recheck the flag before dispatch."""
        site = self.site(True)
        step_up(request)
        item = models.AlertRoute.objects.filter(site=site, pk=route_id).first()
        if not item:
            raise NotFound()
        item.enabled = inputs(EnabledInput, request)["enabled"]
        item.save(update_fields=["enabled"])
        record(
            "notification.route_enabled",
            actor=request.user,
            organisation=site.organisation,
            site=site,
            subject=item.pk,
            after={"enabled": item.enabled},
        )
        return Response(self.get_serializer(item).data)


class AttemptSerializer(serializers.ModelSerializer):
    """Sanitized provider outcomes preserve attempt number and time without raw exceptions."""

    class Meta:
        """All recorded outcomes are immutable/read-only."""

        model = models.NotificationAttempt
        fields = ["number", "occurred_at", "outcome", "error_code"]
        read_only_fields = fields


class NotificationSerializer(serializers.ModelSerializer):
    """Expose provider state separately from incident human acknowledgement."""

    history = AttemptSerializer(many=True, read_only=True)

    class Meta:
        """Source scope, intent and outcomes cannot be edited through the read API."""

        model = models.Notification
        fields = [
            "id",
            "route",
            "contact",
            "event",
            "level",
            "envelope",
            "status",
            "due_at",
            "attempts",
            "provider_reference",
            "history",
        ]
        read_only_fields = fields


class NotificationsView(TelemetryView):
    """Inspect persisted queue, retries and terminal uncertain/dead states."""

    serializer_class = NotificationSerializer

    @extend_schema(responses=NotificationSerializer(many=True))
    def get(self, request, org_id, site_id):
        """Limit evidence to exact site before pagination and prefetch bounded attempt history."""
        return self.listing(
            models.Notification.objects.filter(site=self.site())
            .prefetch_related("history")
            .order_by("-created_at", "id")
        )


class RouteTest(TelemetryView):
    """Persist a clearly marked TEST drill with no industrial incident side effect."""

    serializer_class = NotificationSerializer

    @extend_schema(request=None, responses={201: NotificationSerializer})
    def post(self, request, org_id, site_id, route_id):
        """Require management/step-up and active verified routes before queuing a local test."""
        site = self.site(True)
        step_up(request)
        route = models.AlertRoute.objects.filter(pk=route_id, site=site, enabled=True).first()
        if not route:
            raise NotFound()
        if not services.eligible(route.contact):
            raise PermissionDenied()
        item = services.enqueue(route, route.contact, "test", timezone.now())
        record(
            "notification.test_requested",
            actor=request.user,
            organisation=site.organisation,
            site=site,
            subject=item.pk,
        )
        return Response(self.get_serializer(item).data, status=201)


class HealthSerializer(serializers.Serializer):
    """Delivery health distinguishes stopped worker, pending work and open support issues."""

    worker = serializers.CharField()
    pending = serializers.IntegerField()
    dead = serializers.IntegerField()
    issues = serializers.IntegerField()
    accepted = serializers.IntegerField()
    issue_reasons = serializers.ListField(child=serializers.CharField())


class HealthView(TelemetryView):
    """Read scoped service health; absent heartbeat never means healthy."""

    serializer_class = HealthSerializer

    def get(self, request, org_id, site_id):
        """Read the expiring worker heartbeat separately from scoped queue/support counts."""
        site = self.site()
        queue = models.Notification.objects.filter(site=site)
        return Response(
            {
                "worker": "running"
                if cache.get("notification-worker-alive")
                else "unknown_or_delayed",
                "pending": queue.filter(
                    status__in=["pending", "retry", "sending", "deferred_maintenance"]
                ).count(),
                "dead": queue.filter(status__in=["dead", "uncertain"]).count(),
                "issues": models.DeliveryIssue.objects.filter(
                    site=site, resolved_at__isnull=True
                ).count(),
                "accepted": queue.filter(status="accepted").count(),
                "issue_reasons": list(
                    models.DeliveryIssue.objects.filter(site=site, resolved_at__isnull=True)
                    .order_by("reason")
                    .values_list("reason", flat=True)
                    .distinct()[:20]
                ),
            }
        )
