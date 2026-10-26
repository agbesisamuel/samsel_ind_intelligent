"""Rule drafts are immutable versions; approval, activation and evaluation are separate evidence."""

from django.conf import settings
from django.db import models

from sii.assets.models import ScopedAsset, Sensor, Zone
from sii.telemetry.models import Reading


class RuleSet(ScopedAsset):
    """One temperature rule family per zone avoids undocumented precedence between overlaps."""

    zone = models.OneToOneField(Zone, on_delete=models.PROTECT)
    name = models.CharField(max_length=160)


class RuleVersion(ScopedAsset):
    """Immutable customer-entered bounds; amendments are new numbered versions, never updates."""

    ruleset = models.ForeignKey(RuleSet, on_delete=models.PROTECT)
    version = models.PositiveIntegerField()
    lower_bound = models.DecimalField(max_digits=12, decimal_places=4)
    upper_bound = models.DecimalField(max_digits=12, decimal_places=4)
    hysteresis = models.DecimalField(max_digits=12, decimal_places=4)
    sustained_sec = models.PositiveIntegerField()
    recovery_sec = models.PositiveIntegerField()
    sop_reference = models.CharField(max_length=240)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(ScopedAsset.Meta):
        """Concurrent draft creation cannot reuse a family version number."""

        constraints = [
            *ScopedAsset.Meta.constraints,
            models.UniqueConstraint(fields=["ruleset", "version"], name="rule_version_number"),
            models.CheckConstraint(
                condition=models.Q(lower_bound__lt=models.F("upper_bound")), name="rule_bounds"
            ),
            models.CheckConstraint(
                condition=models.Q(hysteresis__gte=0), name="rule_hysteresis_positive"
            ),
        ]


class RuleBacktest(ScopedAsset):
    """Preserved preview with input/time range hash; never a safety validation."""

    version = models.ForeignKey(RuleVersion, on_delete=models.PROTECT)
    start = models.DateTimeField()
    end = models.DateTimeField()
    result = models.JSONField()
    input_hash = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class RuleApproval(ScopedAsset):
    """QA approval binds a version to a tested result and timing policy snapshot."""

    version = models.OneToOneField(RuleVersion, on_delete=models.PROTECT)
    backtest = models.ForeignKey(RuleBacktest, on_delete=models.PROTECT)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    approved_at = models.DateTimeField(auto_now_add=True)
    snapshot = models.JSONField()
    snapshot_hash = models.CharField(max_length=64)
    synthetic = models.BooleanField(default=True, editable=False)


class RuleActivation(ScopedAsset):
    """Immutable effective boundary; the next activation supersedes the previous one."""

    ruleset = models.ForeignKey(RuleSet, on_delete=models.PROTECT)
    approval = models.OneToOneField(RuleApproval, on_delete=models.PROTECT)
    effective_at = models.DateTimeField()

    class Meta(ScopedAsset.Meta):
        """Serialized half-open effective intervals cannot have an ambiguous equal start time."""

        constraints = [
            *ScopedAsset.Meta.constraints,
            models.UniqueConstraint(
                fields=["ruleset", "effective_at"], name="rule_effective_unique"
            ),
        ]


class RuleCursor(ScopedAsset):
    """Rebuildable per-version/sensor stream position; late data never rewinds incident evidence."""

    version = models.ForeignKey(RuleVersion, on_delete=models.PROTECT)
    sensor = models.ForeignKey(Sensor, on_delete=models.PROTECT)
    state = models.JSONField(default=dict, blank=True)

    class Meta(ScopedAsset.Meta):
        """One serialized deterministic state machine per sensor and rule version."""

        constraints = [
            *ScopedAsset.Meta.constraints,
            models.UniqueConstraint(fields=["version", "sensor"], name="rule_cursor_unique"),
        ]


class RuleEvaluation(ScopedAsset):
    """Idempotent immutable result for one rule/input; late and invalid inputs remain visible."""

    version = models.ForeignKey(RuleVersion, on_delete=models.PROTECT)
    reading = models.ForeignKey(Reading, on_delete=models.PROTECT)
    result = models.JSONField()
    evaluated_at = models.DateTimeField(auto_now_add=True)

    class Meta(ScopedAsset.Meta):
        """A worker retry cannot evaluate or open another incident for the same input twice."""

        constraints = [
            *ScopedAsset.Meta.constraints,
            models.UniqueConstraint(fields=["version", "reading"], name="rule_evaluation_unique"),
        ]


class SuppressionWindow(ScopedAsset):
    """Explicit expiring maintenance scope; preserves observations and visible incident evidence."""

    sensor = models.ForeignKey(Sensor, on_delete=models.PROTECT, null=True, blank=True)
    start = models.DateTimeField()
    end = models.DateTimeField()
    reason = models.CharField(max_length=500)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(ScopedAsset.Meta):
        """Maintenance cannot have a reversed/empty range, even through bulk writes."""

        constraints = [
            *ScopedAsset.Meta.constraints,
            models.CheckConstraint(
                condition=models.Q(end__gt=models.F("start")), name="suppression_range"
            ),
        ]
