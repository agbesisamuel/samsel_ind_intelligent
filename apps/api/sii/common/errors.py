"""Stable error envelopes; internal exceptions and infrastructure secrets stay private."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def envelope(request, code, message, details=None):
    """Build a public error body without exposing request content or exception reprs."""
    return {
        "code": code,
        "message": message,
        "details": details or {},
        "request_id": getattr(request, "request_id", ""),
    }


def exception_handler(exc, context):
    """Convert recognized DRF errors; let Django handle unexpected faults generically."""
    if isinstance(exc, (ValidationError, IntegrityError)):
        # Model validation/constraint errors may include another object's identifier.
        # Keep concurrency and nested-scope failures bounded and non-disclosing.
        return Response(
            envelope(context["request"], "validation_error", "Invalid or conflicting data."),
            status=409 if isinstance(exc, IntegrityError) else 400,
        )
    response = drf_exception_handler(exc, context)
    if response is not None:
        code = getattr(exc, "default_code", "request_error")
        response.data = envelope(
            context["request"], code, str(getattr(exc, "default_detail", "Request failed."))
        )
    return response


def not_found(request, exception):
    """Return the same non-disclosing response for every unknown resource."""
    return JsonResponse(envelope(request, "not_found", "Resource not found."), status=404)


def server_error(request):
    """Hide exception details when an unexpected server error escapes a view."""
    return JsonResponse(envelope(request, "server_error", "Request failed."), status=500)


def csrf_failure(request, reason=""):
    """Return the stable envelope without reflecting an untrusted Origin or middleware reason."""
    from sii.audit.services import record

    record("csrf.denied")
    return JsonResponse(
        envelope(request, "csrf_denied", "Request verification failed."), status=403
    )
