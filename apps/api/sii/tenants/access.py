"""Reusable fail-closed scopes for HTTP and background services; staff flags grant no data."""

from django.db.models import Q
from rest_framework.exceptions import NotFound, PermissionDenied

from sii.audit.services import record

from .models import Membership, Organisation, Role, RoleAssignment, Site

PRIVILEGED_ROLES = [Role.OWNER, Role.SITE_ADMIN, Role.QA]


def assignments(user):
    """Return only currently active membership grants, recalculated on every request."""
    if not user or not user.is_authenticated or not user.is_active:
        return RoleAssignment.objects.none()
    return RoleAssignment.objects.filter(membership__user=user, membership__active=True)


def organisations_for(user):
    """Scope organisation metadata to active assignments; never use a submitted org as authority."""
    return Organisation.objects.filter(id__in=assignments(user).values("organisation_id"))


def sites_for(user, organisation_id=None, roles=None):
    """Scope sites for HTTP/worker callers; owners see their organisation, staff have no bypass."""
    grants = assignments(user)
    if organisation_id:
        grants = grants.filter(organisation_id=organisation_id)
    owners = grants.filter(role=Role.OWNER).values("organisation_id")
    site_grants = grants.exclude(role=Role.OWNER)
    if roles is not None:
        site_grants = site_grants.filter(role__in=roles)
    return Site.objects.filter(
        Q(organisation_id__in=owners) | Q(id__in=site_grants.values("site_id"))
    )


def scoped_org(user, organisation_id):
    """Use indistinguishable scoped 404s for absent and foreign organisations."""
    result = organisations_for(user).filter(pk=organisation_id).first()
    if result is None:
        record("scope.denied", actor=user)
        raise NotFound()
    return result


def is_owner(user, organisation):
    """Check a live organisation-wide owner assignment, not just membership or staff status."""
    return assignments(user).filter(organisation=organisation, role=Role.OWNER).exists()


def require_owner(user, organisation):
    """Deny and record attempts to manage organisation-wide configuration without ownership."""
    if not is_owner(user, organisation):
        record("permission.denied", actor=user, organisation=organisation)
        raise PermissionDenied()


def can_assign(user, organisation, role, site):
    """Owners manage all scopes; site admins only grant nonprivileged roles in assigned sites."""
    if site and site.organisation_id != organisation.id:
        raise NotFound()
    if (role == Role.OWNER) != (site is None):
        raise PermissionDenied("Invalid role scope.")
    if is_owner(user, organisation):
        return
    if (
        role in PRIVILEGED_ROLES
        or not site
        or not sites_for(user, organisation.id, [Role.SITE_ADMIN]).filter(pk=site.pk).exists()
    ):
        record("role.denied", actor=user, organisation=organisation)
        raise PermissionDenied()


def members_for(user, organisation):
    """Only owners may list global member identities; site administrators see their sites."""
    members = Membership.objects.filter(organisation=organisation)
    if is_owner(user, organisation):
        return members
    scopes = sites_for(user, organisation.id, [Role.SITE_ADMIN])
    return members.filter(roles__site__in=scopes).distinct()
