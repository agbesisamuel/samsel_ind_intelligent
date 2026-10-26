"""PostgreSQL-backed tests with isolated caches and no external email delivery."""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

if ENVIRONMENT != "test":  # noqa: F405
    raise ImproperlyConfigured("Test settings require SII_ENV=test.")
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
