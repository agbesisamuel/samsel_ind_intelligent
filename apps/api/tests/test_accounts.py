"""Protect the initial identity schema without implementing Sprint 02 workflows."""

import uuid

import pytest
from django.db import IntegrityError, transaction

from sii.accounts.models import CustomUser

pytestmark = pytest.mark.django_db


def test_user_has_uuid_canonical_email_and_unusable_default_password():
    """Offline identity creation cannot accidentally create a usable shared password."""
    user = CustomUser.objects.create_user("  Person@Example.Invalid  ")
    assert isinstance(user.pk, uuid.UUID)
    assert user.email == "person@example.invalid"
    assert not user.has_usable_password()
    assert not user.is_staff


def test_case_insensitive_uniqueness_applies_to_bulk_writes():
    """Database constraints protect callers that bypass model save normalization."""
    CustomUser.objects.create_user("person@example.invalid")
    with pytest.raises(IntegrityError), transaction.atomic():
        CustomUser.objects.bulk_create([CustomUser(email="PERSON@example.invalid")])


def test_empty_email_rejected_by_manager_and_database():
    """Neither ordinary creation nor direct bulk insert may persist an empty identity."""
    with pytest.raises(ValueError):
        CustomUser.objects.create_user(" ")
    with pytest.raises(IntegrityError), transaction.atomic():
        CustomUser.objects.bulk_create([CustomUser(email="")])


def test_superuser_requires_both_privilege_flags():
    """Administrative creation rejects inconsistent flag combinations."""
    with pytest.raises(ValueError):
        CustomUser.objects.create_superuser("admin@example.invalid", is_staff=False)
