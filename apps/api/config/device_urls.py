"""Dedicated TLS listener exposes only device ingress and scoped receipts."""

from django.urls import path

from sii.telemetry.device_views import IngestView, ReceiptView

urlpatterns = [
    path("api/v1/device/ingest/", IngestView.as_view()),
    path("api/v1/device/receipts/<uuid:event_id>/", ReceiptView.as_view()),
]
