"""Versioned global plans, tenant subscriptions and immutable manual finance drafts."""

from django.conf import settings
from django.db import models
from django.utils import timezone

from sii.tenants.models import TenantModel


class Plan(models.Model):
    """Immutable technical templates; changed limits require a new version/code."""

    code = models.SlugField(primary_key=True, max_length=40)
    name = models.CharField(max_length=100)
    max_sites = models.PositiveIntegerField()
    max_sensors = models.PositiveIntegerField()
    max_sensors_per_site = models.PositiveIntegerField()
    features = models.JSONField(default=list)


class SubscriptionState(models.TextChoices):
    """Commercial metadata never changes a site's independent monitoring lifecycle."""

    TRIAL = "trial", "trial"
    PILOT = "pilot", "pilot"
    ACTIVE = "active", "active"
    PAST_DUE = "past_due", "past_due"
    ENDING = "ending", "ending"
    ENDED = "ended", "ended"


class Subscription(TenantModel):
    """One quota authority per tenant; lock this row before counting expansion capacity."""

    organisation = models.OneToOneField("tenants.Organisation", on_delete=models.PROTECT)
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    state = models.CharField(max_length=20, choices=SubscriptionState.choices, default="trial")
    starts_at = models.DateTimeField(default=timezone.now, editable=False)
    ends_at = models.DateTimeField(null=True, blank=True)
    billing_name = models.CharField(max_length=160, blank=True)
    billing_email = models.EmailField(blank=True)
    purchase_reference = models.CharField(max_length=80, blank=True)
    synthetic = models.BooleanField(default=True, editable=False)

    class Meta:
        """Composite identity supports immutable tenant-bound subscription history."""

        constraints = [
            models.UniqueConstraint(fields=["id", "organisation"], name="subscription_scope"),
            models.CheckConstraint(
                condition=models.Q(ends_at__isnull=True)
                | models.Q(ends_at__gte=models.F("starts_at")),
                name="subscription_dates",
            ),
            models.CheckConstraint(
                condition=models.Q(state__in=SubscriptionState.values), name="subscription_state"
            ),
            models.CheckConstraint(
                condition=models.Q(synthetic=True), name="subscription_local_only"
            ),
        ]


class SubscriptionChange(TenantModel):
    """Append-only original commercial change/reason, separate from current projections."""

    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT)
    before = models.JSONField()
    after = models.JSONField()
    reason = models.CharField(max_length=500)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)


class Currency(models.TextChoices):
    """Manual nominal amounts only; no exchange rates, tax advice or automatic charging."""

    DKK = "DKK", "DKK"
    EUR = "EUR", "EUR"
    USD = "USD", "USD"


class InvoiceDraft(TenantModel):
    """Immutable finance-review draft, not an issued/paid invoice or accounting integration."""

    reference = models.CharField(max_length=40)
    period_start = models.DateField()
    period_end = models.DateField()
    currency = models.CharField(max_length=3, choices=Currency.choices)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)
    synthetic = models.BooleanField(default=True, editable=False)

    class Meta:
        """Draft identity, period, nonnegative amounts and local provenance survive raw writes."""

        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "reference"], name="invoice_reference_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(period_end__gte=models.F("period_start")), name="invoice_period"
            ),
            models.CheckConstraint(
                condition=models.Q(net_amount__gte=0, tax_amount__gte=0), name="invoice_nonnegative"
            ),
            models.CheckConstraint(
                condition=models.Q(currency__in=Currency.values), name="invoice_currency"
            ),
            models.CheckConstraint(condition=models.Q(synthetic=True), name="invoice_local_only"),
        ]
