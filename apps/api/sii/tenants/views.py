"""Tenant/site administration APIs; every queryset is scoped and every mutation is audited."""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from sii.accounts.security import VerifiedUser, step_up
from sii.accounts.views import inputs
from sii.audit.models import AuditEvent
from sii.audit.services import record

from .access import (
    can_assign,
    is_owner,
    members_for,
    organisations_for,
    require_owner,
    scoped_org,
    sites_for,
)
from .models import Invitation, Membership, Organisation, Role, RoleAssignment, Site
from .serializers import (
    AuditSerializer,
    InvitationInput,
    InvitationSerializer,
    MembershipInput,
    MembershipSerializer,
    MeSerializer,
    OrganisationSerializer,
    ProvisionInput,
    RoleInput,
    RoleSerializer,
    SiteSerializer,
)
from .services import issue_invitation


class ScopedView(GenericAPIView):
    """Require verified sessions and explicit scoped services, never unrestricted CRUD."""

    permission_classes = [VerifiedUser]

    def handle_exception(self, exc):
        """Persist denied-command evidence after inner transactions unwind; never log payloads."""
        response = super().handle_exception(exc)
        if 400 <= response.status_code < 500:
            record("request.denied", actor=self.request.user)
        return response

    def organisation(self):
        """Resolve the URL organisation through current user membership before any nested lookup."""
        return scoped_org(self.request.user, self.kwargs["org_id"])

    def listing(self, queryset):
        """Apply consistent bounded pagination and serializer context to every collection."""
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    def finalize_response(self, request, response, *args, **kwargs):
        """Prevent caching customer identities or scopes across session changes."""
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response


class MeView(ScopedView):
    """Return only the caller's current identity and granted memberships."""

    serializer_class = MeSerializer

    def get(self, request):
        """Client capabilities are hints; server queries always recalculate permissions."""
        user = request.user
        return Response(
            self.get_serializer(
                {
                    "id": user.pk,
                    "email": user.email,
                    "mfa_enabled": user.mfa_enabled,
                    "platform_admin": user.is_superuser,
                    "memberships": Membership.objects.filter(user=user, active=True).order_by("id"),
                }
            ).data
        )


class OrganisationListView(ScopedView):
    """Platform administrators provision metadata; customer users list only their organisations."""

    serializer_class = OrganisationSerializer

    @extend_schema(responses=OrganisationSerializer(many=True))
    def get(self, request):
        """No staff bypass to tenant sites/data; explicit platform list contains only metadata."""
        items = (
            Organisation.objects.all()
            if request.user.is_superuser
            else organisations_for(request.user)
        )
        return self.listing(items.order_by("name", "id"))

    @extend_schema(request=ProvisionInput, responses={201: OrganisationSerializer})
    def post(self, request):
        """Provision an organisation with a mailed owner invite after fresh platform MFA."""
        step_up(request)
        if not request.user.is_superuser:
            raise PermissionDenied()
        data = inputs(ProvisionInput, request)
        with transaction.atomic():
            organisation = Organisation.objects.create(name=data["name"])
            record(
                "organisation.created",
                actor=request.user,
                organisation=organisation,
                subject=organisation.pk,
            )
            issue_invitation(organisation, data["owner_email"], Role.OWNER, actor=request.user)
        return Response(self.get_serializer(organisation).data, status=201)


class OrganisationDetailView(ScopedView):
    """Membership-scoped metadata with owner-only audited configuration changes."""

    serializer_class = OrganisationSerializer

    def get(self, request, org_id):
        """Return scoped metadata; foreign and nonexistent IDs have the same 404."""
        return Response(self.get_serializer(self.organisation()).data)

    def patch(self, request, org_id):
        """Keep customer ownership fixed and audit the before/after configuration hashes."""
        organisation = self.organisation()
        require_owner(request.user, organisation)
        step_up(request)
        with transaction.atomic():
            organisation = Organisation.objects.select_for_update().get(pk=organisation.pk)
            before = self.get_serializer(organisation).data
            serializer = self.get_serializer(organisation, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            record(
                "organisation.updated",
                actor=request.user,
                organisation=organisation,
                subject=organisation.pk,
                before=before,
                after=serializer.data,
            )
        return Response(serializer.data)


class SiteListView(ScopedView):
    """List exact granted sites; only owners add sites to their organisation."""

    serializer_class = SiteSerializer

    @extend_schema(responses=SiteSerializer(many=True))
    def get(self, request, org_id):
        """Scope before pagination so counts cannot reveal unrelated sites."""
        organisation = self.organisation()
        return self.listing(sites_for(request.user, organisation.pk).order_by("name", "id"))

    def post(self, request, org_id):
        """Create planned-only sites; no request can activate real monitoring."""
        organisation = self.organisation()
        require_owner(request.user, organisation)
        step_up(request)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            from sii.billing.services import ensure_capacity

            ensure_capacity(organisation.pk, "site")
            site = serializer.save(organisation=organisation)
            record(
                "site.created",
                actor=request.user,
                organisation=organisation,
                site=site,
                subject=site.pk,
                after=serializer.data,
            )
        return Response(serializer.data, status=201)


class SiteDetailView(ScopedView):
    """Exact site read/write scope, including nested URL consistency."""

    serializer_class = SiteSerializer

    def get_site(self, write=False):
        """Resolve within the organisation and appropriate role; never unrestricted get(pk)."""
        organisation = self.organisation()
        site = (
            sites_for(self.request.user, organisation.pk, [Role.SITE_ADMIN] if write else None)
            .filter(pk=self.kwargs["site_id"])
            .first()
        )
        if not site:
            raise NotFound()
        return site

    def get(self, request, org_id, site_id):
        """Return an allowed site without broadening scope from a query/body override."""
        return Response(self.get_serializer(self.get_site()).data)

    def patch(self, request, org_id, site_id):
        """Archive/configure without deleting historic references or modifying service state."""
        site = self.get_site(write=True)
        step_up(request)
        with transaction.atomic():
            site = Site.objects.select_for_update().get(pk=site.pk, organisation_id=org_id)
            before = self.get_serializer(site).data
            serializer = self.get_serializer(site, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            if site.archived and serializer.validated_data.get("archived") is False:
                from sii.billing.services import ensure_capacity

                ensure_capacity(site.organisation_id, "site")
            serializer.save()
            record(
                "site.updated",
                actor=request.user,
                organisation=site.organisation,
                site=site,
                subject=site.pk,
                before=before,
                after=serializer.data,
            )
        return Response(serializer.data)


class MemberListView(ScopedView):
    """Management-only identities, with nested role serialization constrained to scope."""

    serializer_class = MembershipSerializer

    @extend_schema(responses=MembershipSerializer(many=True))
    def get(self, request, org_id):
        """Return an empty list to nonmanagers, never another site's identity roster."""
        return self.listing(members_for(request.user, self.organisation()).order_by("id"))


class MemberDetailView(ScopedView):
    """Owners deactivate/reactivate memberships; identities and history remain intact."""

    serializer_class = MembershipSerializer

    @extend_schema(request=MembershipInput, responses=MembershipSerializer)
    def patch(self, request, org_id, membership_id):
        """Prevent last-owner removal; all subsequent requests recheck active membership."""
        organisation = self.organisation()
        require_owner(request.user, organisation)
        step_up(request)
        data = inputs(MembershipInput, request)
        with transaction.atomic():
            Organisation.objects.select_for_update().get(pk=organisation.pk)
            member = Membership.objects.filter(pk=membership_id, organisation=organisation).first()
            if not member:
                raise NotFound()
            if (
                not data["active"]
                and member.roles.filter(role=Role.OWNER).exists()
                and not RoleAssignment.objects.filter(
                    organisation=organisation, role=Role.OWNER, membership__active=True
                )
                .exclude(membership=member)
                .exists()
            ):
                raise ValidationError("Keep at least one active owner.")
            before = member.active
            member.active = data["active"]
            member.save()
            record(
                "membership.updated",
                actor=request.user,
                organisation=organisation,
                subject=member.pk,
                before=before,
                after=member.active,
            )
        return Response(self.get_serializer(member).data)


class InvitationListView(ScopedView):
    """Manage invitations without revealing tokens or unrelated-site invitees."""

    serializer_class = InvitationSerializer

    @extend_schema(responses=InvitationSerializer(many=True))
    def get(self, request, org_id):
        """Return only invitations the manager could manage within their current scope."""
        organisation = self.organisation()
        items = Invitation.objects.filter(organisation=organisation)
        if not is_owner(request.user, organisation):
            items = items.filter(site__in=sites_for(request.user, org_id, [Role.SITE_ADMIN]))
        return self.listing(items.order_by("-expires_at", "id"))

    @extend_schema(request=InvitationInput, responses={201: InvitationSerializer})
    def post(self, request, org_id):
        """Authorize offered privileges before issuing the email proof, with recent MFA."""
        organisation = self.organisation()
        step_up(request)
        data = inputs(InvitationInput, request)
        site = Site.objects.filter(organisation=organisation, pk=data["site_id"]).first()
        if data["site_id"] and not site:
            raise NotFound()
        can_assign(request.user, organisation, data["role"], site)
        invitation = issue_invitation(organisation, data["email"], data["role"], site, request.user)
        return Response(self.get_serializer(invitation).data, status=201)


class InvitationRevokeView(ScopedView):
    """Revoke pending email proofs while retaining invitation and audit history."""

    serializer_class = InvitationSerializer

    @extend_schema(request=None, responses=InvitationSerializer)
    def post(self, request, org_id, invitation_id):
        """Scope and lock the invitation before revoking it; accepted memberships are separate."""
        organisation = self.organisation()
        step_up(request)
        with transaction.atomic():
            invitation = (
                Invitation.objects.select_for_update()
                .filter(organisation=organisation, pk=invitation_id)
                .first()
            )
            if not invitation:
                raise NotFound()
            can_assign(request.user, organisation, invitation.role, invitation.site)
            invitation.revoked_at = timezone.now()
            invitation.save(update_fields=["revoked_at"])
            record(
                "invitation.revoked",
                actor=request.user,
                organisation=organisation,
                site=invitation.site,
                subject=invitation.pk,
            )
        return Response(self.get_serializer(invitation).data)


class RoleGrantView(ScopedView):
    """Role grants require fresh MFA and two consistent tenant-scoped foreign keys."""

    serializer_class = RoleSerializer

    @extend_schema(request=RoleInput, responses={201: RoleSerializer})
    def post(self, request, org_id):
        """Lock organisation edits; new privilege cannot bypass the next session assurance check."""
        organisation = self.organisation()
        step_up(request)
        data = inputs(RoleInput, request)
        with transaction.atomic():
            Organisation.objects.select_for_update().get(pk=organisation.pk)
            member = Membership.objects.filter(
                organisation=organisation, pk=data["membership_id"], active=True
            ).first()
            site = Site.objects.filter(organisation=organisation, pk=data["site_id"]).first()
            if not member or (data["site_id"] and not site):
                raise NotFound()
            can_assign(request.user, organisation, data["role"], site)
            role, _ = RoleAssignment.objects.get_or_create(
                organisation=organisation, membership=member, site=site, role=data["role"]
            )
            record(
                "role.granted",
                actor=request.user,
                organisation=organisation,
                site=site,
                subject=role.pk,
                after={"role": role.role},
            )
        return Response(self.get_serializer(role).data, status=201)


class RoleRevokeView(ScopedView):
    """Revoke a grant explicitly; immutable audit preserves who changed its scope."""

    serializer_class = RoleSerializer

    @extend_schema(request=None, responses={204: None})
    def post(self, request, org_id, role_id):
        """Retain at least one owner and forbid site-admin escalation through nested role IDs."""
        organisation = self.organisation()
        step_up(request)
        with transaction.atomic():
            Organisation.objects.select_for_update().get(pk=organisation.pk)
            role = RoleAssignment.objects.filter(organisation=organisation, pk=role_id).first()
            if not role:
                raise NotFound()
            can_assign(request.user, organisation, role.role, role.site)
            if (
                role.role == Role.OWNER
                and not RoleAssignment.objects.filter(
                    organisation=organisation, role=Role.OWNER, membership__active=True
                )
                .exclude(pk=role.pk)
                .exists()
            ):
                raise ValidationError("Keep at least one active owner.")
            record(
                "role.revoked",
                actor=request.user,
                organisation=organisation,
                site=role.site,
                subject=role.pk,
                before={"role": role.role},
            )
            role.delete()
        return Response(status=204)


class AuditListView(ScopedView):
    """Paginated evidence restricted to owner or granted site admin/QA/auditor scopes."""

    serializer_class = AuditSerializer

    @extend_schema(responses=AuditSerializer(many=True))
    def get(self, request, org_id):
        """Global auth events are never included in customer timelines or staff browse APIs."""
        organisation = self.organisation()
        events = AuditEvent.objects.filter(organisation=organisation)
        if not is_owner(request.user, organisation):
            allowed = sites_for(request.user, org_id, [Role.SITE_ADMIN, Role.QA, Role.AUDITOR])
            events = events.filter(Q(site__in=allowed))
        return self.listing(events)
