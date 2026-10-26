"""Encrypt bounded local database/object backups; stdout carries bytes only in explicit pipe modes.

Keys stay in environment, never in the archive or CLI. The same verifier can run
inside an isolated restore network with a fresh database and object store.
"""

import base64
import hashlib
import json
import os
import sys
from pathlib import Path

import django
from cryptography.fernet import Fernet, InvalidToken

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
django.setup()

from django.conf import settings  # noqa: E402
from django.db import IntegrityError, connection, transaction  # noqa: E402
from django.db.models import Max  # noqa: E402
from django.utils import timezone  # noqa: E402

from sii.audit.models import AuditEvent  # noqa: E402
from sii.audit.verification import verify  # noqa: E402
from sii.billing.models import InvoiceDraft, Plan, Subscription, SubscriptionChange  # noqa: E402
from sii.common import storage  # noqa: E402
from sii.incidents.models import EvidenceAttachment  # noqa: E402
from sii.reports.models import ReportJob  # noqa: E402
from sii.support.models import SupportTicket, TicketEvent  # noqa: E402
from sii.telemetry.models import Reading  # noqa: E402
from sii.tenants.models import Organisation  # noqa: E402

LIMIT = 256 * 1024 * 1024


def cipher():
    """Use a distinct 256-bit backup key; missing key fails before processing plaintext."""
    key = bytes.fromhex(os.environ["BACKUP_ENCRYPTION_KEY"])
    if len(key) != 32 or key == bytes.fromhex(settings.EVIDENCE_ENCRYPTION_KEY):
        raise ValueError("Independent backup key required")
    return Fernet(base64.urlsafe_b64encode(key))


def read_input():
    """Bound development memory use; larger deployments require streaming backup tooling."""
    value = sys.stdin.buffer.read(LIMIT + 1)
    if len(value) > LIMIT:
        raise ValueError("Backup exceeds local bound")
    return value


def seal(payload):
    """Combine a custom-format pg_dump with immutable encrypted object bytes and seal the bundle."""
    if connection.settings_dict["NAME"] != "sii_local":
        raise ValueError("Source must be local")
    body = json.loads(payload)
    dump = base64.b64decode(body["dump"], validate=True)
    if not dump.startswith(b"PGDMP"):
        raise ValueError("Custom-format PostgreSQL dump required")
    body["dump_hash"] = hashlib.sha256(dump).hexdigest()
    objects, size = [], len(payload)
    s3 = storage.client()
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=storage.BUCKET):
        for item in page.get("Contents", []):
            parts = item["Key"].split("/")
            if len(parts) != 3 or storage.key_for(*parts) != item["Key"]:
                raise ValueError("Unexpected object identity")
            stream = s3.get_object(Bucket=storage.BUCKET, Key=item["Key"])["Body"]
            try:
                raw = stream.read(storage.LIMIT * 2 + 1)
            finally:
                stream.close()
            size += len(raw) * 2
            if len(raw) > storage.LIMIT * 2 or size > LIMIT // 2 or len(objects) >= 10000:
                raise ValueError("Reduce local backup scope or use approved streaming backup")
            objects.append(
                {
                    "key": item["Key"],
                    "ciphertext": base64.b64encode(raw).decode(),
                    "hash": hashlib.sha256(raw).hexdigest(),
                }
            )
    body["objects"] = objects
    return cipher().encrypt(json.dumps(body, sort_keys=True).encode())


def unseal(payload):
    """Reject corrupt/wrong-key backup before restoring either database or objects."""
    body = json.loads(cipher().decrypt(payload))
    dump = base64.b64decode(body["dump"], validate=True)
    if hashlib.sha256(dump).hexdigest() != body["dump_hash"]:
        raise ValueError("Backup dump checksum mismatch")
    return body, dump


def selftest():
    """Prove corruption and a different key fail authentication without exposing plaintext."""
    dump = b"PGDMP synthetic authentication probe"
    body = {"dump": base64.b64encode(dump).decode(), "dump_hash": hashlib.sha256(dump).hexdigest()}
    encrypted = cipher().encrypt(json.dumps(body).encode())
    assert unseal(encrypted)[1] == dump
    corrupt = encrypted[:-8] + b"AAAAAAAA"
    for token in [corrupt, Fernet(Fernet.generate_key()).encrypt(json.dumps(body).encode())]:
        try:
            unseal(token)
        except InvalidToken:
            continue
        raise AssertionError("Unauthenticated backup accepted")
    print("Backup corruption and wrong-key authentication checks passed")


def restore_verify(payload):
    """Restore objects in the isolated target and verify actual application decryption."""
    if (
        connection.settings_dict["NAME"] != "sii_restore"
        or connection.settings_dict["HOST"] != "restore-db"
    ):
        raise ValueError("Requires isolated restore target")
    body, _ = unseal(payload)
    s3 = storage.client()
    s3.create_bucket(Bucket=storage.BUCKET)
    for item in body["objects"]:
        parts = item["key"].split("/")
        if len(parts) != 3 or storage.key_for(*parts) != item["key"]:
            raise ValueError("Backup object scope mismatch")
        raw = base64.b64decode(item["ciphertext"], validate=True)
        if hashlib.sha256(raw).hexdigest() != item["hash"]:
            raise ValueError("Backup object checksum mismatch")
        s3.put_object(Bucket=storage.BUCKET, Key=item["key"], Body=raw, IfNoneMatch="*")
    # Compare pre-snapshot external checkpoints; later concurrent appends may legitimately
    # exist in the dump, but no captured audit prefix may be missing or changed.
    for head in body["checkpoint"]["chains"]:
        if head["sequence"]:
            event = AuditEvent.objects.get(
                organisation_id=None if head["chain"] == "global" else head["chain"],
                sequence=head["sequence"],
            )
            if event.event_hash != head["hash"]:
                raise ValueError("External audit checkpoint mismatch")
    chains = verify()
    # Exercise restored SQL protection as the database owner, only on this fresh
    # target. Roll back even a failed guard so the restored snapshot stays intact.
    guarded = False
    try:
        with transaction.atomic():
            Plan.objects.filter(pk="local-trial-v1").update(name="SYNTHETIC forbidden change")
            transaction.set_rollback(True)
    except IntegrityError:
        guarded = True
    if not guarded or Subscription.objects.count() != Organisation.objects.count():
        raise ValueError("Restored commercial defaults/immutability failed")
    commercial = {
        "plans": Plan.objects.count(),
        "subscriptions": Subscription.objects.count(),
        "term_changes": SubscriptionChange.objects.count(),
        "invoice_drafts": InvoiceDraft.objects.count(),
        "support_tickets": SupportTicket.objects.count(),
        "ticket_events": TicketEvent.objects.count(),
        "catalog_immutability_verified": guarded,
    }
    artifacts = 0
    for model, filter in [(ReportJob, {"status": "ready"}), (EvidenceAttachment, {})]:
        for item in model.objects.filter(**filter).iterator():
            storage.get(item.organisation_id, item.site_id, item.pk, item.checksum)
            artifacts += 1
    return {
        "chains_verified": len(chains),
        "readings_restored": Reading.objects.count(),
        "objects_restored": len(body["objects"]),
        "artifacts_decrypted": artifacts,
        "commercial_support": commercial,
        "checkpoint_at": body["checkpoint"]["at"],
        "latest_audit_at": AuditEvent.objects.aggregate(latest=Max("occurred_at"))[
            "latest"
        ].isoformat(),
        "verified_at": timezone.now().isoformat(),
    }


def main():
    """Expose pipe-only modes; callers capture binary stdout rather than displaying it."""
    if settings.ENVIRONMENT != "local":
        raise ValueError("Local-only drill")
    mode = sys.argv[1]
    if mode == "checkpoint":
        print(json.dumps({"at": timezone.now().isoformat(), "chains": verify()}))
    elif mode == "seal":
        sys.stdout.buffer.write(seal(read_input()))
    elif mode == "dump":
        sys.stdout.buffer.write(unseal(read_input())[1])
    elif mode == "verify":
        print(json.dumps(restore_verify(read_input())))
    elif mode == "selftest":
        selftest()
    else:
        raise ValueError("Unknown backup mode")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Backup/restore failed (sensitive details redacted).", file=sys.stderr)
        raise SystemExit(1) from None
