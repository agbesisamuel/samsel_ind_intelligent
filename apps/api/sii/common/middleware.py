"""Server-generated correlation identifiers without trusting inbound log content."""

import uuid


class RequestIdMiddleware:
    """Attach a new opaque request ID and disable caching of API responses."""

    def __init__(self, get_response):
        """Store the next Django middleware handler."""
        self.get_response = get_response

    def __call__(self, request):
        """Generate a UUID rather than echoing arbitrary attacker-supplied headers."""
        request.request_id = str(uuid.uuid4())
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        if request.path.startswith("/api/"):
            response["Cache-Control"] = "no-store"
            # JSON/download APIs need no active content. Preserve stricter attachment
            # sandbox policies already set by evidence/report handlers.
            if "Content-Security-Policy" not in response:
                response["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
            response["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response
