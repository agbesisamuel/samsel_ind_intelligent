"""Minimal unauthenticated process/database probes; never represent site safety."""

from django.db import DatabaseError, connection
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class StatusSerializer(serializers.Serializer):
    """A single status label, without versions, hostnames, credentials or tenant data."""

    status = serializers.ChoiceField(choices=["ok", "ready", "unavailable"])


class HealthView(APIView):
    """Check process liveness without touching infrastructure or customer data."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(responses={200: StatusSerializer}, auth=[])
    def get(self, request):
        """Return a fixed liveness response; does not imply monitoring is operational."""
        return Response({"status": "ok"})


class ReadinessView(HealthView):
    """Check PostgreSQL connectivity; queue/storage health belongs to stack checks."""

    @extend_schema(responses={200: StatusSerializer, 503: StatusSerializer}, auth=[])
    def get(self, request):
        """Execute a bounded read-only probe and redact database errors on failure."""
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except DatabaseError:
            return Response({"status": "unavailable"}, status=503)
        return Response({"status": "ready"})
