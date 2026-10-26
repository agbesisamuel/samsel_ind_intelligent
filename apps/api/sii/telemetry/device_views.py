"""TLS-only device HTTP surface: no human sessions, administration or tenant selectors."""

import hmac
import io
import uuid

from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .contracts import Event, Receipt
from .models import Reading
from .security import active_credential, secret_for
from .services import ingest


class BoundedJSONParser(JSONParser):
    """Limit bytes read even without Content-Length; reject oversized device messages."""

    def parse(self, stream, media_type=None, parser_context=None):
        """Read at most 64 KiB plus one sentinel byte before invoking the strict JSON parser."""
        data = stream.read(65537)
        if len(data) > 65536:
            raise ValidationError("Payload exceeds 64 KiB.")
        return super().parse(io.BytesIO(data), media_type, parser_context)


class DeviceView(APIView):
    """Authentication is separate from cookies and bound to the encrypted connection."""

    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = [BoundedJSONParser]

    def credential(self, request):
        """Reject plaintext, wrong scheme and malformed credentials without revealing existence."""
        if not request.is_secure():
            raise PermissionDenied("TLS required.")
        try:
            scheme, token = request.headers.get("Authorization", "").split(" ", 1)
            identifier, secret = token.split(".", 1)
            credential = active_credential(uuid.UUID(identifier))
            if (
                scheme != "Device"
                or not credential
                or not hmac.compare_digest(secret_for(credential), secret)
            ):
                raise ValueError()
        except (ValueError, TypeError):
            raise AuthenticationFailed("Invalid device credential.") from None
        return credential


class IngestView(DeviceView):
    """Single event or bounded batch; every returned accepted receipt is already committed."""

    @extend_schema(request=Event, responses=Receipt(many=True))
    def post(self, request):
        """No all-or-nothing batch claim: receipts identify each independently durable event."""
        credential = self.credential(request)
        events = request.data if isinstance(request.data, list) else [request.data]
        if not 1 <= len(events) <= 100:
            raise ValidationError("Batch must contain 1–100 events.")
        return Response([ingest(credential, payload, "https") for payload in events], status=200)


class ReceiptView(DeviceView):
    """MQTT publishers can check application persistence independently from broker PUBACK."""

    @extend_schema(responses=Receipt)
    def get(self, request, event_id):
        """Resolve only this gateway's records; unknown/foreign events remain indistinguishable."""
        credential = self.credential(request)
        item = Reading.objects.filter(
            organisation=credential.organisation,
            site=credential.site,
            gateway=credential.gateway,
            event_id=event_id,
        ).first()
        return Response(
            {"status": "accepted", "reading_id": str(item.pk)}
            if item
            else {"status": "not_persisted"}
        )
