"""Bounded auth input and explicit secret-free output contracts for the first-party portal."""

from rest_framework import serializers


class LoginInput(serializers.Serializer):
    """Passwords are write-only and never echoed in responses or validation details."""

    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=256, write_only=True, trim_whitespace=False)


class TokenInput(serializers.Serializer):
    """One-time proof plus password; secrets only travel in protected request bodies."""

    token = serializers.CharField(max_length=128, write_only=True)
    password = serializers.CharField(max_length=256, write_only=True, trim_whitespace=False)


class EmailInput(serializers.Serializer):
    """Bounded email for non-enumerating password reset requests."""

    email = serializers.EmailField(max_length=254)


class MFAInput(serializers.Serializer):
    """TOTP or recovery proof; password is additionally required for step-up."""

    code = serializers.CharField(max_length=128, write_only=True, required=False, default="")
    password = serializers.CharField(
        max_length=256, write_only=True, required=False, default="", trim_whitespace=False
    )


class AuthResult(serializers.Serializer):
    """Challenge state is not authentication; only complete grants a business session."""

    state = serializers.ChoiceField(choices=["complete", "mfa", "enroll", "accepted", "signed_out"])
    secret = serializers.CharField(required=False)
    provisioning_uri = serializers.CharField(required=False)
    recovery_codes = serializers.ListField(child=serializers.CharField(), required=False)


class CSRFResult(serializers.Serializer):
    """Masked CSRF token is required for all unsafe first-party endpoints, including login."""

    csrf_token = serializers.CharField()
