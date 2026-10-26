"""Explicit commercial metadata scope, immutable manual drafts and formula-safe CSV exports."""

import csv
import io
from datetime import timedelta

from django.db import transaction
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from sii.accounts.security import step_up
from sii.accounts.views import inputs
from sii.audit.services import record
from sii.tenants.access import require_owner
from sii.tenants.serializers import StrictInputMixin
from sii.tenants.views import ScopedView

from . import services
from .models import (
    Currency,
    InvoiceDraft,
    Plan,
    Subscription,
    SubscriptionChange,
    SubscriptionState,
)


class PlanSerializer(serializers.ModelSerializer):
    """Immutable server catalog; no frontend prices or asserted commercial validation."""

    class Meta:
        """Supported capabilities and expansion limits are source-controlled."""

        model = Plan
        fields = ["code", "name", "max_sites", "max_sensors", "max_sensors_per_site", "features"]
        read_only_fields = fields


class PlansView(ScopedView):
    """Authenticated catalog metadata grants no customer-data access."""

    serializer_class = PlanSerializer

    @extend_schema(responses=PlanSerializer(many=True))
    def get(self, request):
        """Return the bounded global technical templates without confidential tenant state."""
        return self.listing(Plan.objects.all().order_by("code"))


class QuotaUsageSerializer(serializers.Serializer):
    """Server-computed counts, never client-provided capacity authority."""

    sites = serializers.IntegerField()
    sensors = serializers.IntegerField()


class QuotaLimitsSerializer(QuotaUsageSerializer):
    """Immutable plan ceilings include organisation totals and a site probe ceiling."""

    sensors_per_site = serializers.IntegerField()


class SubscriptionStatus(serializers.Serializer):
    """Owner/platform commercial view; site operators never see aggregate tenant billing data."""

    plan = serializers.CharField()
    state = serializers.ChoiceField(choices=SubscriptionState.choices)
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField(allow_null=True)
    billing_name = serializers.CharField(allow_blank=True)
    billing_email = serializers.EmailField(allow_blank=True)
    purchase_reference = serializers.CharField(allow_blank=True)
    usage = QuotaUsageSerializer()
    limits = QuotaLimitsSerializer()
    warnings = serializers.ListField(child=serializers.CharField())
    expansion_allowed = serializers.BooleanField()
    live_collections_enabled = serializers.BooleanField()
    monitoring_suspended = serializers.BooleanField()
    synthetic = serializers.BooleanField()


class TermsInput(StrictInputMixin, serializers.Serializer):
    """Platform-only local terms change with recorded purpose; no collection-provider fields."""

    plan = serializers.SlugField(max_length=40)
    state = serializers.ChoiceField(choices=SubscriptionState.choices)
    ends_at = serializers.DateTimeField(allow_null=True)
    reason = serializers.CharField(min_length=8, max_length=500)

    def validate_ends_at(self, value):
        """Require an explicit offset instead of guessing an ambiguous local term boundary."""
        raw = self.initial_data.get("ends_at")
        if raw is not None and not (
            isinstance(raw, str) and (raw.endswith("Z") or "+" in raw[10:] or "-" in raw[10:])
        ):
            raise serializers.ValidationError("Use an explicit timestamp offset")
        return value


class BillingSettingsInput(StrictInputMixin, serializers.Serializer):
    """Owner-controlled contact/reference fields; no bank/card/token or plan escalation input."""

    billing_name = serializers.CharField(max_length=160, allow_blank=True)
    billing_email = serializers.EmailField(allow_blank=True)
    purchase_reference = serializers.CharField(max_length=80, allow_blank=True)


class SubscriptionView(ScopedView):
    """A narrow metadata exception for commercial admins does not grant ordinary site scope."""

    serializer_class = SubscriptionStatus

    def get(self, request, org_id):
        """Resolve an owner or explicit platform commercial identity before querying usage."""
        organisation = services.commercial_org(request.user, org_id)
        return Response(
            services.status(
                Subscription.objects.select_related("plan").get(organisation=organisation)
            )
        )

    @extend_schema(request=TermsInput, responses=SubscriptionStatus)
    def post(self, request, org_id):
        """Only platform admins with recent MFA may change plan/state/term metadata."""
        organisation = services.commercial_org(request.user, org_id, platform_only=True)
        step_up(request)
        return Response(
            services.status(
                services.change(organisation, request.user, inputs(TermsInput, request))
            )
        )

    @extend_schema(request=BillingSettingsInput, responses=SubscriptionStatus)
    @transaction.atomic
    def patch(self, request, org_id):
        """Owners amend billing contact details; plan/state fields are rejected, not ignored."""
        organisation = self.organisation()
        require_owner(request.user, organisation)
        step_up(request)
        data = inputs(BillingSettingsInput, request)
        subscription = Subscription.objects.select_for_update().get(organisation=organisation)
        for key, value in data.items():
            setattr(subscription, key, value)
        subscription.save(update_fields=list(data))
        record(
            "billing.settings_updated",
            actor=request.user,
            organisation=organisation,
            subject=subscription.pk,
            after=data,
        )
        return Response(services.status(subscription))


class InvoiceSerializer(serializers.ModelSerializer):
    """Original local finance draft; payment/approval state cannot be fabricated."""

    class Meta:
        """Amounts are nominal entered values; no exchange/tax rate is supplied."""

        model = InvoiceDraft
        fields = [
            "id",
            "reference",
            "period_start",
            "period_end",
            "currency",
            "net_amount",
            "tax_amount",
            "recorded_at",
            "recorded_by",
            "synthetic",
        ]
        read_only_fields = fields


class TermsChangeSerializer(serializers.ModelSerializer):
    """Immutable local term change history for the same owner/platform commercial scope."""

    class Meta:
        """Preserve original actor, reason and before/after term snapshots."""

        model = SubscriptionChange
        fields = ["id", "before", "after", "reason", "recorded_by", "recorded_at"]
        read_only_fields = fields


class TermsHistory(ScopedView):
    """Commercial history access grants no site content or membership authority."""

    serializer_class = TermsChangeSerializer

    @extend_schema(responses=TermsChangeSerializer(many=True))
    def get(self, request, org_id):
        """Scope before paginating immutable local changes."""
        organisation = services.commercial_org(request.user, org_id)
        return self.listing(
            SubscriptionChange.objects.filter(organisation=organisation).order_by(
                "-recorded_at", "-id"
            )
        )


class InvoiceInput(StrictInputMixin, serializers.Serializer):
    """Manual draft fields only, with bounded dates and nonnegative finance-entered amounts."""

    reference = serializers.RegexField(r"^[A-Z][A-Z0-9-]{1,39}$")
    period_start = serializers.DateField()
    period_end = serializers.DateField()
    currency = serializers.ChoiceField(choices=Currency.choices)
    net_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    tax_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)

    def validate(self, data):
        """Reject reversed periods and aggregation beyond one year."""
        if not timedelta(0) <= data["period_end"] - data["period_start"] <= timedelta(days=366):
            raise serializers.ValidationError("Choose a period up to 366 days")
        return data


class InvoicesView(ScopedView):
    """Owners read/export their drafts; platform commercial admins record them explicitly."""

    serializer_class = InvoiceSerializer

    @extend_schema(responses=InvoiceSerializer(many=True))
    def get(self, request, org_id):
        """Scope precedes pagination and invoice reference disclosure."""
        organisation = services.commercial_org(request.user, org_id)
        return self.listing(
            InvoiceDraft.objects.filter(organisation=organisation).order_by("-recorded_at", "-id")
        )

    @extend_schema(request=InvoiceInput, responses={201: InvoiceSerializer})
    def post(self, request, org_id):
        """Preserve idempotent reference/content; never call an accounting/payment service."""
        organisation = services.commercial_org(request.user, org_id, platform_only=True)
        step_up(request)
        draft = services.invoice(organisation, request.user, inputs(InvoiceInput, request))
        return Response(self.get_serializer(draft).data, status=201)


def csv_cell(value):
    """Neutralize spreadsheet formulas even if a future text field starts with whitespace."""
    value = str(value)
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


class InvoiceExport(ScopedView):
    """One bounded, authenticated manual draft per download; source history is unchanged."""

    serializer_class = InvoiceSerializer

    @extend_schema(responses={(200, "text/csv"): bytes})
    def get(self, request, org_id, invoice_id):
        """Recheck current commercial scope and audit before returning a formula-safe attachment."""
        organisation = services.commercial_org(request.user, org_id)
        draft = InvoiceDraft.objects.filter(organisation=organisation, pk=invoice_id).first()
        if not draft:
            raise NotFound()
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(
            [
                "document_type",
                "organisation_id",
                "reference",
                "period_start",
                "period_end",
                "currency",
                "net_amount",
                "tax_amount",
                "total_amount",
            ]
        )
        writer.writerow(
            [
                csv_cell(value)
                for value in [
                    "SYNTHETIC_FINANCE_DRAFT",
                    organisation.pk,
                    draft.reference,
                    draft.period_start,
                    draft.period_end,
                    draft.currency,
                    draft.net_amount,
                    draft.tax_amount,
                    draft.net_amount + draft.tax_amount,
                ]
            ]
        )
        record(
            "invoice.draft_exported",
            actor=request.user,
            organisation=organisation,
            subject=draft.pk,
        )
        response = HttpResponse(
            stream.getvalue().encode("utf-8-sig"), content_type="text/csv; charset=utf-8"
        )
        response["Content-Disposition"] = 'attachment; filename="invoice-draft.csv"'
        return response
