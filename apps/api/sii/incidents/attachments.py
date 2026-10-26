"""Constrained external evidence: UTF-8 plain text only, encrypted before private storage."""

import uuid

from django.db import transaction
from rest_framework.exceptions import ValidationError

from sii.audit.services import record
from sii.common import storage

from .models import EvidenceAttachment
from .workflow import append, locked, require_responder


def validate_upload(upload):
    """Accept at most 64 KiB plain UTF-8; reject active types, controls and malware test input.

    No HTML/PDF/office/archive/image parser executes untrusted content. Downloads use
    a server-owned .txt filename and attachment disposition. Additional formats need
    a separately tested malware scanning/re-encoding pipeline before being enabled.
    """
    if not upload.name.lower().endswith(".txt") or upload.content_type != "text/plain":
        raise ValidationError("Only UTF-8 .txt evidence is enabled.")
    body = upload.read(65537)
    if not 0 < len(body) <= 65536:
        raise ValidationError("Evidence must be 1..65536 bytes.")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("Evidence must be UTF-8 text.") from exc
    if (
        any(ord(char) < 32 and char not in "\n\r\t" for char in text)
        or "<" in text
        or ">" in text
        or "EICAR-STANDARD-ANTIVIRUS-TEST-FILE" in text
    ):
        raise ValidationError("Active markup, controls and executable test content are rejected.")
    return body


def attach(incident, user, upload, label, revision):
    """Store encrypted evidence and append history; clean only this new object on rollback."""
    require_responder(user, incident.site)
    body = validate_upload(upload)
    identifier = uuid.uuid4()
    key = None
    try:
        with transaction.atomic():
            item = locked(incident)
            if item.revision != revision or item.status == "closed":
                raise ValidationError("Refresh the open incident before attaching evidence.")
            key, checksum = storage.put(item.organisation_id, item.site_id, identifier, body)
            evidence = EvidenceAttachment.objects.create(
                id=identifier,
                organisation=item.organisation,
                site=item.site,
                incident=item,
                object_key=key,
                checksum=checksum,
                size=len(body),
                label=label,
                uploaded_by=user,
            )
            if item.status == "qa_reviewed":
                item.status = "awaiting_qa"
            append(
                item,
                user,
                "incident.evidence_attached.v1",
                {"attachment": str(evidence.pk), "checksum": checksum, "label": label},
            )
            return evidence
    except Exception:
        if key:
            try:
                storage.discard(incident.organisation_id, incident.site_id, identifier)
            except Exception:
                # Retain an auditable orphan marker rather than hiding failed cleanup.
                record(
                    "evidence.orphan_cleanup_failed",
                    actor=user,
                    organisation=incident.organisation,
                    site=incident.site,
                    subject=identifier,
                )
        raise
