"""Protect public probe contracts, failure redaction and fail-closed authorization."""

import uuid
from unittest.mock import patch

import pytest
from django.db import OperationalError
from rest_framework.response import Response
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from sii.accounts.models import CustomUser


def test_health_is_minimal_and_does_not_trust_request_ids():
    """Probe stays data-free and does not reflect attacker-controlled headers."""
    response = APIClient().get("/api/v1/health/", HTTP_X_REQUEST_ID="untrusted")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    uuid.UUID(response["X-Request-ID"])
    assert response["Cache-Control"] == "no-store"
    assert response["X-Content-Type-Options"] == "nosniff"


@pytest.mark.django_db
def test_readiness_uses_real_database():
    """A real PostgreSQL connection must succeed before readiness reports ready."""
    response = APIClient().get("/api/v1/ready/")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_database_outage_is_unavailable_without_exception_details():
    """A DB outage must not look healthy or disclose credentials in its error."""
    with patch("sii.common.views.connection.cursor", side_effect=OperationalError("sensitive")):
        response = APIClient().get("/api/v1/ready/")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert b"sensitive" not in response.content


@pytest.mark.parametrize("path", ["/admin/", "/api/v1/device-ingest/telemetry/"])
def test_future_data_paths_are_not_exposed(path):
    """Unimplemented data paths remain absent, irrespective of spoofed tenant IDs."""
    response = APIClient().get(path, {"organisation_id": str(uuid.uuid4())})
    assert response.status_code == 404
    assert set(response.json()) == {"code", "message", "details", "request_id"}


@pytest.mark.parametrize("staff", [False, True])
def test_default_permission_denies_authenticated_users_including_staff(staff):
    """New views cannot accidentally inherit staff or authenticated-user access."""

    class UnscopedView(APIView):
        """A deliberately policy-free view used to verify the global default."""

        def get(self, request):
            """Return a sentinel that must be unreachable without explicit permission."""
            return Response({"data": "must never escape"})

    request = APIRequestFactory().get("/")
    force_authenticate(
        request,
        user=CustomUser(email="fictional@example.invalid", is_staff=staff, is_superuser=staff),
    )
    response = UnscopedView.as_view()(request)
    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"


def test_health_rejects_mutation():
    """Public health is read-only; POST never performs a command."""
    response = APIClient().post("/api/v1/health/", {}, format="json")
    assert response.status_code == 405
    assert response.json()["code"] == "method_not_allowed"


def test_openapi_is_versioned_and_has_only_implemented_domains():
    """The generated contract includes identity but never advertises unimplemented telemetry."""
    response = APIClient().get("/api/v1/schema/?format=json")
    assert response.status_code == 200
    assert response.json()["openapi"] == "3.1.0"
    paths = set(response.json()["paths"])
    assert {"/api/v1/health/", "/api/v1/ready/", "/api/v1/me/"} <= paths
    assert not any("device-ingest" in path for path in paths)
