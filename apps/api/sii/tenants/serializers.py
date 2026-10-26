"""Explicit tenant administration contracts; ownership and activation are never mass-assignable."""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from sii.audit.models import AuditEvent

from .models import Invitation, Membership, Organisation, Role, RoleAssignment, Site


class StrictInputMixin:
    """Reject unknown and read-only input rather than silently ignoring spoofed scope fields."""

    def to_internal_value(self, data):
        """Limit writable keys to the advertised contract before model validation."""
        allowed = {name for name, field in self.fields.items() if not field.read_only}
        if not isinstance(data, dict) or set(data) - allowed:
            raise serializers.ValidationError(
                {"non_field_errors": ["Unsupported or read-only fields."]}
            )
        return super().to_internal_value(data)


class OrganisationSerializer(StrictInputMixin, serializers.ModelSerializer):
    """Organisation metadata only; no embedded customer readings or users."""

    class Meta:
        """Country/timezone are configurable; activation and demo provenance are protected."""

        model = Organisation
        fields = ["id", "name", "country_code", "timezone_default", "contract_status", "is_demo"]
        read_only_fields = ["id", "contract_status", "is_demo"]


class ProvisionInput(StrictInputMixin, serializers.Serializer):
    """Platform provisioning sends an owner invitation; no known initial password is created."""

    name = serializers.CharField(max_length=160)
    owner_email = serializers.EmailField(max_length=254)


class SiteSerializer(StrictInputMixin, serializers.ModelSerializer):
    """Sites remain planned until later qualified commissioning; PATCH cannot activate them."""

    class Meta:
        """Immutable organisation and service state cannot be supplied through the API."""

        model = Site
        fields = ["id", "organisation", "name", "timezone", "service_state", "archived"]
        read_only_fields = ["id", "organisation", "service_state"]
        # The service supplies organisation and model/DB constraints enforce uniqueness.
        validators = []


class RoleSerializer(serializers.ModelSerializer):
    """Return only the role's exact organisation/site scope."""

    class Meta:
        """Permission changes use a separate validated command."""

        model = RoleAssignment
        fields = ["id", "role", "site"]
        read_only_fields = fields


class MembershipSerializer(serializers.ModelSerializer):
    """Membership output filters nested roles to the caller's permitted sites."""

    email = serializers.EmailField(source="user.email", read_only=True)
    roles = serializers.SerializerMethodField()

    class Meta:
        """Never serialize a password, TOTP seed, recovery hash or identity security version."""

        model = Membership
        fields = ["id", "organisation", "email", "active", "roles"]
        read_only_fields = fields

    @extend_schema_field(RoleSerializer(many=True))
    def get_roles(self, membership) -> list[dict]:
        """Avoid leaking unrelated-site grants through a visible member's nested roles."""
        from .access import is_owner, sites_for

        user = self.context["request"].user
        roles = membership.roles.all()
        if not is_owner(user, membership.organisation) and membership.user_id != user.pk:
            roles = roles.filter(
                site__in=sites_for(user, membership.organisation_id, [Role.SITE_ADMIN])
            )
        return RoleSerializer(roles, many=True).data


class InvitationInput(StrictInputMixin, serializers.Serializer):
    """Inviters select an exact role and site, with authority checked by the service."""

    email = serializers.EmailField(max_length=254)
    role = serializers.ChoiceField(choices=Role.choices)
    site_id = serializers.UUIDField(required=False, allow_null=True, default=None)


class InvitationSerializer(serializers.ModelSerializer):
    """Invitation state visible to managers; token hashes and bearer tokens are excluded."""

    class Meta:
        """Expose sufficient state for expiry/revocation without granting acceptance authority."""

        model = Invitation
        fields = ["id", "email", "role", "site", "expires_at", "accepted_at", "revoked_at"]
        read_only_fields = fields


class RoleInput(StrictInputMixin, serializers.Serializer):
    """Grant an exact scope to an existing membership; no cross-tenant nested identifiers."""

    membership_id = serializers.UUIDField()
    site_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    role = serializers.ChoiceField(choices=Role.choices)


class MembershipInput(StrictInputMixin, serializers.Serializer):
    """Membership deactivation preserves historical identity and audit references."""

    active = serializers.BooleanField()


class AuditSerializer(serializers.ModelSerializer):
    """Read-only timeline exposes identifiers and evidence hashes, never secret snapshots."""

    class Meta:
        """No audit update/delete API exists."""

        model = AuditEvent
        fields = [
            "id",
            "organisation",
            "site",
            "actor",
            "action",
            "subject",
            "occurred_at",
            "sequence",
            "before_hash",
            "after_hash",
            "prev_hash",
            "event_hash",
        ]
        read_only_fields = fields


class MeSerializer(serializers.Serializer):
    """Authenticated identity and current memberships, without deriving client authority."""

    id = serializers.UUIDField()
    email = serializers.EmailField()
    mfa_enabled = serializers.BooleanField()
    platform_admin = serializers.BooleanField()
    memberships = MembershipSerializer(many=True)
