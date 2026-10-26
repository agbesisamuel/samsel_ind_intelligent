"""One strict event contract shared by HTTPS, MQTT, CSV and deterministic simulators."""

from datetime import timedelta

from rest_framework import serializers

from sii.tenants.serializers import StrictInputMixin


class Event(StrictInputMixin, serializers.Serializer):
    """Offsets are mandatory; engineering limits are not food-safety thresholds."""

    version = serializers.ChoiceField(choices=[1])
    event_id = serializers.UUIDField()
    sensor_id = serializers.UUIDField()
    sequence = serializers.IntegerField(min_value=0, max_value=9223372036854775807)
    observed_at = serializers.DateTimeField()
    value = serializers.DecimalField(max_digits=12, decimal_places=4)
    unit = serializers.ChoiceField(choices=["degC"])

    def validate_observed_at(self, value):
        """Reject ambiguous local timestamps instead of guessing a DST offset."""
        raw = self.initial_data.get("observed_at", "")
        if not isinstance(raw, str) or not (
            raw.endswith("Z") or "+" in raw[10:] or "-" in raw[10:]
        ):
            raise serializers.ValidationError("An explicit UTC offset is required.")
        return value


class Receipt(serializers.Serializer):
    """Application receipt represents committed storage, distinct from an MQTT PUBACK."""

    status = serializers.CharField()
    reading_id = serializers.UUIDField(required=False)
    reason = serializers.CharField(required=False)


class TimeWindow(serializers.Serializer):
    """Shared bounded observation/backtest window with explicit UTC offsets."""

    start = serializers.DateTimeField()
    end = serializers.DateTimeField()

    def validate(self, data):
        """Reject ambiguous local timestamps and windows exceeding 31 days."""
        for key in ["start", "end"]:
            raw = self.initial_data[key]
            if not (raw.endswith("Z") or "+" in raw[10:] or "-" in raw[10:]):
                raise serializers.ValidationError("Use explicit timestamp offsets.")
        if not timedelta(0) < data["end"] - data["start"] <= timedelta(days=31):
            raise serializers.ValidationError("Choose a positive window up to 31 days.")
        return data


class ReadingWindow(TimeWindow):
    """Bind a bounded time window to an exact scoped sensor."""

    sensor = serializers.UUIDField()
