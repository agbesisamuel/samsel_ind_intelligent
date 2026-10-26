"""Read-only infrastructure integration checks from inside the API container.

No email, object or business event is created. Infrastructure status is separate
from monitoring readiness. Exceptions are reduced to check names to hide secrets.
"""

import os
import smtplib
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

import django
from redis import Redis

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
# An external script entrypoint does not automatically include the API package root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
django.setup()

from django.conf import settings  # noqa: E402
from django.db import connection  # noqa: E402

from config.celery import app  # noqa: E402


def database():
    """Verify PostgreSQL query round-trip without reading customer tables."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)


def broker():
    """Authenticate to RabbitMQ and ask the worker for a bounded control ping."""
    with app.connection_for_read() as conn:
        conn.ensure_connection(max_retries=0)
    assert app.control.inspect(timeout=5).ping()


def cache():
    """Authenticate and ping Redis without using it as durable business storage."""
    with Redis.from_url(settings.REDIS_URL, socket_timeout=3) as client:
        assert client.ping()


def storage():
    """Verify S3 denies anonymous clients and internal storage ports are unreachable."""
    try:
        with urllib.request.urlopen("http://object-store:8333/", timeout=5):
            raise AssertionError("Anonymous S3 access must be denied")
    except urllib.error.HTTPError as exc:
        assert exc.code == 403
    # These HTTP/gRPC endpoints could bypass S3 authorization if exposed to peers.
    for port in [9333, 19333, 8080, 18080, 8888, 18888, 18333, 7333, 23646, 8181, 9101]:
        with socket.socket() as probe:
            probe.settimeout(2)
            assert probe.connect_ex(("object-store", port)) != 0
    # Docker's separate internal network must not advertise the backend to API peers.
    try:
        socket.getaddrinfo("object-store-backend", 8333)
    except socket.gaierror:
        pass
    else:
        raise AssertionError("Storage backend must not share the application network")


def smtp():
    """Verify the local mail sink responds; never send a notification."""
    with smtplib.SMTP("smtp", 1025, timeout=5) as client:
        assert client.noop()[0] == 250


if __name__ == "__main__":
    failed = False
    for check in [database, broker, cache, storage, smtp]:
        try:
            check()
        except Exception:  # noqa: BLE001 — redact third-party exceptions containing connection secrets.
            print(f"FAIL {check.__name__} (details redacted)")
            failed = True
        else:
            print(f"PASS {check.__name__}")
    sys.exit(1 if failed else 0)
