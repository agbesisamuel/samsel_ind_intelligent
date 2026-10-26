"""Device-only secrets and broker ACL provisioning; human cookies are never accepted here."""

import base64
import hashlib
import hmac
import json
import os
import secrets
import urllib.request
from datetime import timedelta
from urllib.error import HTTPError
from urllib.parse import quote

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from sii.audit.services import record

from .models import DeviceCredential


def cipher():
    """Use a distinct 256-bit environment key; missing/malformed configuration fails closed."""
    return Fernet(base64.urlsafe_b64encode(bytes.fromhex(settings.DEVICE_ENCRYPTION_KEY)))


def secret_for(credential):
    """Decrypt only inside transport authentication/provisioning, never in API serializers."""
    return cipher().decrypt(credential.encrypted_secret.encode()).decode()


def canonical(payload):
    """Stable UTF-8 signing format shared with the simulator; reject NaN/Infinity."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def signature(secret, payload):
    """Authenticate the exact canonical event body using SHA-256 HMAC."""
    return hmac.new(secret.encode(), canonical(payload), hashlib.sha256).hexdigest()


def broker(method, path, body=None):
    """Call fixed private management endpoint; errors expose no credentials or response body."""
    auth = base64.b64encode(
        (os.environ["RABBITMQ_DEFAULT_USER"] + ":" + os.environ["RABBITMQ_DEFAULT_PASS"]).encode()
    ).decode()
    request = urllib.request.Request(
        "http://rabbitmq:15672/api/" + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Basic " + auth, "Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status


def username(credential):
    """Use a public opaque identifier as broker identity, not a human email or secret."""
    return "gw_" + credential.id.hex


def provision(gateway, actor, days=30):
    """Create fail-closed pending state, install exact topic ACL, then reveal a secret once.

    An interrupted broker setup leaves a non-active application credential. A broker
    orphan cannot pass application authentication and is visible as pending metadata.
    """
    secret = secrets.token_urlsafe(32)
    credential = DeviceCredential.objects.create(
        organisation=gateway.organisation,
        site=gateway.site,
        gateway=gateway,
        encrypted_secret=cipher().encrypt(secret.encode()).decode(),
        expires_at=timezone.now() + timedelta(days=days),
    )
    name = username(credential)
    broker("PUT", "users/" + name, {"password": secret, "tags": []})
    broker(
        "PUT",
        "topic-permissions/telemetry/" + name,
        {
            "exchange": "amq.topic",
            "write": "^ingest\\." + credential.id.hex + "$",
            "read": "^$",
        },
    )
    broker(
        "PUT",
        "permissions/telemetry/" + name,
        {
            "configure": "^$",
            "write": "^amq\\.topic$",
            "read": "^$",
        },
    )
    credential.provisioned = True
    credential.save(update_fields=["provisioned"])
    record(
        "device.credential_issued",
        actor=actor,
        organisation=gateway.organisation,
        site=gateway.site,
        subject=credential.pk,
    )
    return credential, secret


def revoke(credential, actor):
    """Commit application revocation before broker cleanup, even if the broker is unavailable."""
    with transaction.atomic():
        item = DeviceCredential.objects.select_for_update().get(pk=credential.pk)
        if item.revoked_at is None:
            item.revoked_at = timezone.now()
            item.save(update_fields=["revoked_at"])
            record(
                "device.credential_revoked",
                actor=actor,
                organisation=item.organisation,
                site=item.site,
                subject=item.pk,
            )
    try:
        broker("DELETE", "users/" + quote(username(item), safe=""))
    except HTTPError as exc:
        if exc.code != 404:
            raise


def active_credential(identifier):
    """Resolve provisioned, unexpired, unrevoked credentials; ingest rechecks the gateway."""
    return (
        DeviceCredential.objects.filter(
            pk=identifier, provisioned=True, revoked_at__isnull=True, expires_at__gt=timezone.now()
        )
        .select_related("gateway", "site", "organisation")
        .first()
    )
