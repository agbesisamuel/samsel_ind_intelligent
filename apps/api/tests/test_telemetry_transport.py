"""Transport-specific negative cases protect durable ACK and broker-authentication boundaries."""

import secrets
from unittest.mock import Mock, patch

import pytest
from django.test import override_settings
from rest_framework.test import APIClient
from test_assets import inventory  # noqa: F401
from test_telemetry import event, qualified  # noqa: F401

from sii.telemetry.models import ProcessingOutbox, Reading, Rejection
from sii.telemetry.security import canonical, signature
from sii.telemetry.services import ingest
from sii.telemetry.transport import dispatch, event_envelope, mqtt_message, run_group, work_message

pytestmark = pytest.mark.django_db


def test_mqtt_signature_and_durable_ack(qualified):  # noqa: F811
    """A valid broker login alone cannot forge another credential's signed event."""
    message = Mock(delivery_info={"routing_key": "ingest." + qualified["credential"].id.hex})
    payload = event(qualified)
    mqtt_message(
        canonical({"event": payload, "signature": signature(secrets.token_urlsafe(32), payload)}),
        message,
    )
    assert Reading.objects.count() == 0
    assert Rejection.objects.get().reason == "signature_invalid"
    message.ack.assert_called_once()
    rejected_event = event_envelope(ProcessingOutbox.objects.get())
    assert rejected_event["event_type"] == "telemetry.rejected.v1"
    message.reset_mock()
    mqtt_message(
        canonical({"event": payload, "signature": signature(qualified["secret"], payload)}), message
    )
    assert Reading.objects.count() == 1
    message.ack.assert_called_once()


def test_event_envelope_scope_is_verified(qualified):  # noqa: F811
    """Even a valid outbox UUID cannot authorize a broker message carrying another tenant scope."""
    ingest(qualified["credential"], event(qualified), "https")
    item = ProcessingOutbox.objects.get()
    message = Mock()
    envelope = event_envelope(item)
    assert envelope["event_type"] == "telemetry.accepted.v1"
    work_message({**envelope, "organisation_id": str(qualified["b"]["organisation"].pk)}, message)
    message.reject.assert_called_once_with(requeue=False)
    item.refresh_from_db()
    assert item.processed_at is None
    message.reset_mock()
    work_message(envelope, message)
    message.ack.assert_called_once()


def test_bounded_device_json(qualified):  # noqa: F811
    """Oversized and non-JSON bodies cannot bypass the device transport's byte bound."""
    client = APIClient()
    auth = f"Device {qualified['credential'].pk}.{qualified['secret']}"
    with override_settings(ROOT_URLCONF="config.device_urls"):
        response = client.post(
            "/api/v1/device/ingest/",
            '{"value":"' + "a" * 65537 + '"}',
            content_type="application/json",
            secure=True,
            HTTP_AUTHORIZATION=auth,
        )
        assert response.status_code == 400
        assert Reading.objects.count() == 0


def test_confirmed_publisher_keeps_one_gateway_on_one_queue(qualified):  # noqa: F811
    """Parallel shards must never split one gateway's ordered stream across consumers."""
    for sequence in [100, 101]:
        ingest(qualified["credential"], event(qualified, sequence=sequence), "https")
    connection = Mock()
    dispatch(connection)
    publications = connection.Producer.return_value.publish.call_args_list
    assert len(publications) == 2
    assert len({call.kwargs["routing_key"] for call in publications}) == 1
    assert all(call.kwargs["delivery_mode"] == 2 for call in publications)
    assert all(item.attempts == 1 for item in ProcessingOutbox.objects.all())


def test_shard_supervisor_stops_own_children_on_failure():
    """A failed child makes the service fail instead of leaving a falsely healthy partial group."""
    children = [Mock() for _ in range(4)]
    children[0].poll.return_value = 1
    for child in children[1:]:
        child.poll.return_value = None
    with patch("sii.telemetry.transport.subprocess.Popen", side_effect=children):
        with pytest.raises(RuntimeError, match="Telemetry shard exited"):
            run_group(0)
    for child in children[1:]:
        child.terminate.assert_called_once()
    for child in children:
        child.wait.assert_called_once_with(timeout=10)


def test_shard_partial_start_failure_reaps_created_children():
    """A process-launch error cannot orphan already started consumers outside supervision."""
    child = Mock()
    child.poll.return_value = None
    with patch("sii.telemetry.transport.subprocess.Popen", side_effect=[child, OSError]):
        with pytest.raises(OSError):
            run_group(0)
    child.terminate.assert_called_once()
    child.wait.assert_called_once_with(timeout=10)
