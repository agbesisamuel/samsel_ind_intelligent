"""Explicit support approvals and narrow diagnostics, separate from ordinary customer routes."""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from sii.accounts.models import CustomUser
from sii.accounts.security import step_up
from sii.accounts.views import inputs
from sii.telemetry.views import TelemetryView
from sii.tenants.access import require_owner
from sii.tenants.serializers import StrictInputMixin
from sii.tenants.views import ScopedView

from . import services
from .models import SupportAccessLog, SupportSession


class SessionSerializer(serializers.ModelSerializer):
    """Customer-visible approval metadata; no implicit role grant is returned."""

    class Meta:
        """Read-only original approval plus revocation state."""

        model = SupportSession
        fields = [
            "id",
            "supporter",
            "approved_by",
            "reason",
            "scope",
            "created_at",
            "expires_at",
            "revoked_at",
        ]
        read_only_fields = fields


class SupportApprovalInput(StrictInputMixin, serializers.Serializer):
    """Explicit staff identity, purpose and lifetime; unknown scopes are rejected."""

    supporter = serializers.UUIDField()
    minutes = serializers.IntegerField(min_value=1, max_value=60)
    reason = serializers.CharField(min_length=8, max_length=500)


class SessionsView(TelemetryView):
    """Only current owners may approve/list support for their selected site."""

    serializer_class = SessionSerializer

    @extend_schema(responses=SessionSerializer(many=True))
    def get(self, request, org_id, site_id):
        """Scope and owner authorization precede support identity disclosure."""
        site = self.site()
        require_owner(request.user, site.organisation)
        return self.listing(SupportSession.objects.filter(site=site).order_by("-created_at"))

    @extend_schema(request=SupportApprovalInput, responses={201: SessionSerializer})
    def post(self, request, org_id, site_id):
        """Recent owner MFA plus independent staff approval; no self-service staff escalation."""
        site = self.site()
        require_owner(request.user, site.organisation)
        step_up(request)
        data = inputs(SupportApprovalInput, request)
        supporter = CustomUser.objects.filter(pk=data.pop("supporter")).first()
        if not supporter:
            raise NotFound()
        return Response(
            self.get_serializer(services.approve(request.user, site, supporter, **data)).data,
            status=201,
        )


class RevokeView(TelemetryView):
    """Immediate revocation is a separate mutation, not an edit to original approval."""

    serializer_class = SessionSerializer

    @extend_schema(request=None, responses=SessionSerializer)
    def post(self, request, org_id, site_id, session_id):
        """Require scoped owner and recent MFA; foreign handles remain indistinguishable."""
        site = self.site()
        require_owner(request.user, site.organisation)
        step_up(request)
        session = SupportSession.objects.filter(site=site, pk=session_id).first()
        if not session:
            raise NotFound()
        return Response(self.get_serializer(services.revoke(request.user, session)).data)


class AccessSerializer(serializers.ModelSerializer):
    """Immutable support access evidence for owner review."""

    class Meta:
        """No delete/edit endpoint exists."""

        model = SupportAccessLog
        fields = ["id", "session", "accessed_at", "action"]
        read_only_fields = fields


class AccessView(TelemetryView):
    """Owners can inspect every scoped support read."""

    serializer_class = AccessSerializer

    @extend_schema(responses=AccessSerializer(many=True))
    def get(self, request, org_id, site_id):
        """Scope before listing; support cannot enumerate customer approval history."""
        site = self.site()
        require_owner(request.user, site.organisation)
        return self.listing(SupportAccessLog.objects.filter(site=site).order_by("-accessed_at"))


class DiagnosticsSerializer(serializers.Serializer):
    """Aggregate counts deliberately exclude evidence contents and personal data."""

    site = serializers.UUIDField()
    scope = serializers.CharField()
    unresolved_incidents = serializers.IntegerField()
    failed_notifications = serializers.IntegerField()
    failed_reports = serializers.IntegerField()


class DiagnosticsView(ScopedView):
    """A separate capability endpoint never alters ordinary tenant queryset authorization."""

    serializer_class = DiagnosticsSerializer

    def get(self, request, session_id):
        """Require recent support MFA and current capability on every read."""
        step_up(request)
        return Response(services.diagnostics(request.user, session_id))
