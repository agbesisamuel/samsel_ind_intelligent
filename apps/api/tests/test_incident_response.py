"""Protect response authority, immutable evidence, replay and encrypted uploads."""

import io
import json
import uuid
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from test_assets import endpoint, inventory  # noqa: F401
from test_identity_tenancy import post, sign_in

from sii.accounts.models import CustomUser
from sii.common import storage
from sii.incidents import attachments
from sii.incidents.models import EvidenceAttachment, IncidentEvent
from sii.incidents.services import observe
from sii.tenants.models import Membership, RoleAssignment

pytestmark = pytest.mark.django_db


@pytest.fixture
def episode(inventory):  # noqa: F811
    """Start an actual synthetic domain episode under an independently QA-granted owner session."""
    a = inventory["a"]
    item = observe(a["gateway"], a["sensor"], "too_warm", timezone.now(), uuid.uuid4(), {})
    return {**inventory, "incident": item, "base": endpoint(a) + f"incidents/{item.pk}/"}


def command(fixture, action, **extra):
    """Submit current revision with a unique replay ID through real CSRF/session authorization."""
    item = fixture["incident"]
    item.refresh_from_db()
    data = {
        "action": action,
        "text": "SYNTHETIC documented human action",
        "revision": item.revision,
        "request_id": str(uuid.uuid4()),
        **extra,
    }
    return post(fixture["client"], fixture["base"] + "commands/", data)


def test_complete_workflow_requires_recovery_and_explicit_qa(episode):
    """Require human workflow and recovery; never auto-close on recovery."""
    item = episode["incident"]
    assert command(episode, "close").status_code == 400
    assert command(episode, "acknowledge").data["status"] == "acknowledged"
    assert command(episode, "investigate").data["status"] == "investigating"
    assert command(episode, "corrective_action").data["status"] == "awaiting_qa"
    assert command(episode, "qa_review").data["status"] == "qa_reviewed"
    assert command(episode, "close").status_code == 400
    observe(item.gateway, item.sensor, item.kind, timezone.now(), uuid.uuid4(), {}, recovered=True)
    item.refresh_from_db()
    assert item.status == "qa_reviewed"
    assert command(episode, "close").data["status"] == "closed"
    assert command(episode, "corrective_action").status_code == 400
    assert command(episode, "amend").data["status"] == "closed"
    assert item.events.filter(kind="incident.resolved.v1").count() == 1
    export = episode["client"].get(episode["base"] + "activity/")
    assert export.status_code == 200 and json.loads(export.content)["synthetic"]
    assert "attachment" in export["Content-Disposition"]


def test_replay_stale_revision_and_qa_independence(episode):
    """Keep retries harmless; reject stale edits, conflicting replays and owner-only QA."""
    payload = {
        "action": "acknowledge",
        "text": "SYNTHETIC acknowledgement",
        "revision": 0,
        "request_id": str(uuid.uuid4()),
    }
    client, url = episode["client"], episode["base"] + "commands/"
    assert post(client, url, payload).status_code == 200
    assert post(client, url, payload).status_code == 200
    assert episode["incident"].events.filter(kind="incident.acknowledged.v1").count() == 1
    assert post(client, url, {**payload, "text": "Changed history forbidden"}).status_code == 400
    assert post(client, url, {**payload, "request_id": str(uuid.uuid4())}).status_code == 400
    command(episode, "investigate")
    command(episode, "corrective_action")
    RoleAssignment.objects.filter(membership=episode["world"]["a"]["member"], role="qa").delete()
    response = command(episode, "qa_review")
    assert response.status_code == 403


def test_recurrence_invalidates_qa_review(episode):
    """Reopen response after renewed breach; retain and invalidate prior QA review."""
    for action in ["acknowledge", "investigate", "corrective_action", "qa_review"]:
        assert command(episode, action).status_code == 200
    item = episode["incident"]
    observe(item.gateway, item.sensor, item.kind, timezone.now(), uuid.uuid4(), {}, recovered=True)
    observe(item.gateway, item.sensor, item.kind, timezone.now(), uuid.uuid4(), {})
    item.refresh_from_db()
    assert item.status == "open" and item.acknowledged_at is None and item.recovered_at is None
    assert item.events.filter(kind="incident.qa_reviewed.v1").exists()
    assert command(episode, "close").status_code == 400


def test_assignment_and_foreign_workflow_scope(episode):
    """Foreign assignees and nested foreign incident IDs fail; auditors cannot mutate response."""
    assert (
        command(episode, "assign", assignee=str(episode["world"]["b"]["user"].pk)).status_code
        == 403
    )
    assert (
        command(episode, "assign", assignee=str(episode["world"]["a"]["user"].pk)).status_code
        == 200
    )
    base = endpoint(episode["b"]) + f"incidents/{episode['incident'].pk}/"
    for suffix in ["", "events/", "activity/", "attachments/", "notifications/"]:
        assert episode["client"].get(base + suffix).status_code == 404
    user = CustomUser.objects.create_user(
        "audit-only@example.invalid", episode["world"]["password"], verified_at=timezone.now()
    )
    member = Membership.objects.create(organisation=episode["a"]["organisation"], user=user)
    RoleAssignment.objects.create(
        organisation=member.organisation,
        membership=member,
        site=episode["a"]["site"],
        role="auditor",
    )
    client, _, _ = sign_in(user, episode["world"]["password"])
    assert command({**episode, "client": client}, "acknowledge").status_code == 403
    assert client.get(episode["base"] + "activity/").status_code == 200
    with pytest.raises(IntegrityError), transaction.atomic():
        IncidentEvent.objects.filter(incident=episode["incident"]).update(evidence={})


class MemoryS3:
    """In-memory object transport fixture; production encryption and integrity code remains real."""

    def __init__(self):
        """Keep only ciphertext indexed by server-owned object key."""
        self.objects = {}

    def create_bucket(self, **kwargs):
        """Provide an isolated already-owned test bucket."""

    def put_object(self, **kwargs):
        """Assert immutable conditional storage and capture encrypted bytes."""
        assert kwargs["IfNoneMatch"] == "*" and kwargs["Key"] not in self.objects
        self.objects[kwargs["Key"]] = kwargs["Body"]

    def get_object(self, **kwargs):
        """Return a closeable body matching the boto response surface."""
        return {"Body": io.BytesIO(self.objects[kwargs["Key"]])}

    def delete_object(self, **kwargs):
        """Delete only the exact newly-created test key."""
        self.objects.pop(kwargs["Key"], None)


def test_attachment_encryption_download_and_review_invalidation(episode):
    """Encrypt before S3; invalidate QA on attachment changes and scope every download."""
    for action in ["acknowledge", "investigate", "corrective_action", "qa_review"]:
        command(episode, action)
    client, item = episode["client"], episode["incident"]
    item.refresh_from_db()
    s3, body = MemoryS3(), b"SYNTHETIC external technician note\n"
    with patch("sii.common.storage.client", return_value=s3):
        csrf = client.get("/api/v1/auth/csrf/").data["csrf_token"]
        response = client.post(
            episode["base"] + "attachments/",
            {
                "file": SimpleUploadedFile("note.txt", body, content_type="text/plain"),
                "label": "Synthetic technician note",
                "revision": item.revision,
            },
            format="multipart",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 201, response.data
        attachment = EvidenceAttachment.objects.get()
        assert body not in s3.objects[attachment.object_key]
        item.refresh_from_db()
        assert item.status == "awaiting_qa"
        path = episode["base"] + f"attachments/{attachment.pk}/download/"
        download = client.get(path)
        assert download.content == body and download["X-Content-Type-Options"] == "nosniff"
        wrong = (
            endpoint(episode["b"]) + f"incidents/{item.pk}/attachments/{attachment.pk}/download/"
        )
        assert client.get(wrong).status_code == 404
        other_id = uuid.uuid4()
        s3.objects[storage.key_for(item.organisation_id, item.site_id, other_id)] = s3.objects[
            attachment.object_key
        ]
        with pytest.raises(ValueError):
            storage.get(item.organisation_id, item.site_id, other_id, attachment.checksum)
        with pytest.raises(IntegrityError), transaction.atomic():
            EvidenceAttachment.objects.update(label="rewrite")


@pytest.mark.parametrize(
    "name,content_type,body",
    [
        ("script.html", "text/html", b"<script>alert(1)</script>"),
        ("fake.txt", "text/plain", b"<svg onload=alert(1)>"),
        ("binary.txt", "text/plain", b"abc\x00def"),
        ("huge.txt", "text/plain", b"x" * 65537),
        ("bad.txt", "text/plain", b"\xff"),
        ("eicar.txt", "text/plain", b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"),
    ],
)
def test_unsafe_attachment_never_reaches_storage(name, content_type, body):
    """Reject active, binary, oversized and invalid-encoding uploads before any object write."""
    with pytest.raises(ValidationError):
        attachments.validate_upload(SimpleUploadedFile(name, body, content_type=content_type))


def test_qa_requires_recent_mfa(episode):
    """A valid session with expired assurance cannot approve or close evidence."""
    for action in ["acknowledge", "investigate", "corrective_action"]:
        command(episode, action)
    session = episode["client"].session
    session["step_up_at"] = 0
    session.save()
    assert command(episode, "qa_review").status_code == 403
