"""Protect complete domain contracts, source scope, duplicate receipts and immutable envelopes."""

import uuid
from unittest.mock import Mock

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from test_assets import inventory  # noqa: F401

from sii.events.models import DomainEvent
from sii.events.services import collect, consume
from sii.incidents.services import observe

pytestmark = pytest.mark.django_db


def test_domain_envelope_scope_and_replay(inventory):  # noqa: F811
    """A source UUID never authorizes changed tenant/site/schema/actor/payload values."""
    a = inventory["a"]
    observe(a["gateway"], a["sensor"], "too_warm", timezone.now(), uuid.uuid4(), {})
    collect()
    event = DomainEvent.objects.get()
    assert set(event.envelope) == {
        "event_id",
        "schema_version",
        "event_type",
        "organisation_id",
        "site_id",
        "occurred_at",
        "correlation_id",
        "actor_or_device_id",
        "payload",
    }
    for key in ["organisation_id", "site_id", "schema_version", "actor_or_device_id", "payload"]:
        message = Mock()
        consume({**event.envelope, key: "foreign"}, message)
        message.reject.assert_called_once_with(requeue=False)
    message = Mock()
    consume(event.envelope, message)
    message.ack.assert_called_once()
    event.refresh_from_db()
    received = event.consumed_at
    consume(event.envelope, Mock())
    event.refresh_from_db()
    assert event.consumed_at == received
    collect()
    assert DomainEvent.objects.count() == 1
    with transaction.atomic(), pytest.raises(IntegrityError):
        DomainEvent.objects.filter(pk=event.pk).update(envelope={})


def test_domain_raw_cross_site_source_denied(inventory):  # noqa: F811
    """Even raw bulk creation must match the immutable source's actual tenant/site."""
    a = inventory["a"]
    observe(a["gateway"], a["sensor"], "too_warm", timezone.now(), uuid.uuid4(), {})
    collect()
    event = DomainEvent.objects.get()
    identifier = uuid.uuid4()
    with transaction.atomic(), pytest.raises(IntegrityError):
        DomainEvent.objects.bulk_create(
            [
                DomainEvent(
                    pk=identifier,
                    organisation=event.organisation,
                    site=inventory["a2"]["site"],
                    source_model=event.source_model,
                    source_id=event.source_id,
                    event_type="incident.opened.v1",
                    available_at=timezone.now(),
                    envelope={
                        **event.envelope,
                        "event_id": str(identifier),
                        "site_id": str(inventory["a2"]["site"].pk),
                    },
                )
            ]
        )
