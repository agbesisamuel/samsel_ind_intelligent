"""Private encrypted S3 evidence with authenticated tenant binding and fixed local endpoint.

Only ciphertext reaches storage. Keys are server-generated UUID paths, not filenames
or URLs. Every read authenticates scope inside the encrypted envelope and verifies
the plaintext checksum. Callers must authorize the persisted metadata first.
"""

import base64
import hashlib
import json
import os
import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

BUCKET = "sii-evidence-local"
LIMIT = 8 * 1024 * 1024


def client():
    """Use signed fixed-endpoint requests; never consult ambient cloud profiles or metadata."""
    if settings.ENVIRONMENT not in {"local", "test"}:
        raise ImproperlyConfigured("Evidence storage is local/test only.")
    return boto3.client(
        "s3",
        endpoint_url="http://object-store:8333",
        region_name="us-east-1",
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=3,
            read_timeout=10,
            retries={"max_attempts": 1},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def cipher():
    """Require the separate 256-bit evidence key; never fall back to session or MFA secrets."""
    try:
        raw = bytes.fromhex(settings.EVIDENCE_ENCRYPTION_KEY)
        if len(raw) != 32:
            raise ValueError()
        return Fernet(base64.urlsafe_b64encode(raw))
    except ValueError as exc:
        raise ImproperlyConfigured("Configure the evidence encryption key.") from exc


def key_for(organisation_id, site_id, identifier):
    """Canonical UUID-only paths prevent traversal, arbitrary buckets and external URL fetches."""
    return "/".join(str(uuid.UUID(str(value))) for value in [organisation_id, site_id, identifier])


def put(organisation_id, site_id, identifier, body):
    """Encrypt bounded immutable bytes; return key/checksum or propagate a storage fault."""
    if not 0 < len(body) <= LIMIT:
        raise ValueError("Evidence size outside limits")
    key = key_for(organisation_id, site_id, identifier)
    checksum = hashlib.sha256(body).hexdigest()
    sealed = cipher().encrypt(
        json.dumps(
            {"key": key, "checksum": checksum, "body": base64.b64encode(body).decode()},
            sort_keys=True,
        ).encode()
    )
    s3 = client()
    try:
        s3.create_bucket(Bucket=BUCKET)
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
            raise
    s3.put_object(
        Bucket=BUCKET, Key=key, Body=sealed, ContentType="application/octet-stream", IfNoneMatch="*"
    )
    return key, checksum


def get(organisation_id, site_id, identifier, checksum):
    """Authenticate scope/content; fail closed on corrupt or swapped ciphertext."""
    key = key_for(organisation_id, site_id, identifier)
    response = client().get_object(Bucket=BUCKET, Key=key)
    stream = response["Body"]
    try:
        sealed = stream.read(LIMIT * 2 + 1)
    finally:
        stream.close()
    if len(sealed) > LIMIT * 2:
        raise ValueError("Oversized stored evidence")
    decoded = json.loads(cipher().decrypt(sealed))
    body = base64.b64decode(decoded["body"], validate=True)
    if (
        decoded["key"] != key
        or decoded["checksum"] != checksum
        or hashlib.sha256(body).hexdigest() != checksum
    ):
        raise ValueError("Evidence integrity mismatch")
    return body


def discard(organisation_id, site_id, identifier):
    """Remove only this new artifact after metadata failure; never sweep prefixes."""
    client().delete_object(Bucket=BUCKET, Key=key_for(organisation_id, site_id, identifier))
