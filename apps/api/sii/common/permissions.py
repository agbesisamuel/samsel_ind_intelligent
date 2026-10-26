"""Fail-closed policy until scoped business permissions are introduced."""

from rest_framework.permissions import BasePermission


class DenyAll(BasePermission):
    """Reject every principal, including superusers, unless a view opts into a policy."""

    def has_permission(self, request, view):
        """Deny access; staff status must never become an implicit tenant bypass."""
        return False
