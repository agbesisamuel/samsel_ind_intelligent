"""UUID user identity established before any other domain migration.

Email comparison is case-insensitive at the database boundary, including bulk
writes. MFA secrets are encrypted separately from password/session material.
"""

import uuid

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower


class UserManager(BaseUserManager):
    """Create email-only identities; missing passwords remain unusable."""

    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        """Normalize email and persist a hashed password, or reject an empty email."""
        if not email or not email.strip():
            raise ValueError("An email is required.")
        user = self.model(email=email.strip().lower(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Create an offline administrative identity; this grants no API bypass."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not extra_fields["is_staff"] or not extra_fields["is_superuser"]:
            raise ValueError("A superuser requires staff and superuser flags.")
        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractUser):
    """Global person identity; tenant authorization must never derive from staff flags."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None
    email = models.EmailField(unique=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    mfa_enabled = models.BooleanField(default=False)
    mfa_secret = models.TextField(blank=True, default="")
    mfa_last_counter = models.BigIntegerField(default=-1)
    recovery_hashes = models.JSONField(default=list)
    auth_version = models.PositiveIntegerField(default=1)
    objects = UserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        """Reject case variants and empty email even when model validation is bypassed."""

        constraints = [
            models.UniqueConstraint(Lower("email"), name="accounts_email_ci_unique"),
            models.CheckConstraint(condition=~models.Q(email=""), name="accounts_email_nonempty"),
        ]

    def save(self, *args, **kwargs):
        """Canonicalize ordinary writes; the unique constraint also protects bulk writes."""
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)


class PasswordReset(models.Model):
    """Single-use random-token digest; reset never removes MFA or grants a session."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True)


class AuthRateBucket(models.Model):
    """Atomic, short-lived rate counter keyed by a hash, never by plaintext email/IP."""

    key = models.CharField(max_length=64, primary_key=True)
    count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)
