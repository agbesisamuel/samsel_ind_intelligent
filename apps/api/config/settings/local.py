"""Loopback HTTP development settings; never reused for non-local deployment."""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

if ENVIRONMENT != "local":  # noqa: F405
    raise ImproperlyConfigured("Local settings require SII_ENV=local.")
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
CSRF_TRUSTED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
