"""Local TLS-only device surface with no human login/admin routes or trusted proxy headers."""

from .local import *  # noqa: F403

ROOT_URLCONF = "config.device_urls"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = None
