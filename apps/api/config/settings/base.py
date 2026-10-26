"""Shared fail-closed configuration for synthetic local/test environments only.

No environment variables enable pilot/production operation. Secret material is
required from the environment; no credentials are embedded in code or fixtures.
"""

import os
from pathlib import Path
from urllib.parse import quote

from django.core.exceptions import ImproperlyConfigured
from kombu import Queue

BASE_DIR = Path(__file__).resolve().parents[2]
ENVIRONMENT = os.environ.get("SII_ENV", "")
if ENVIRONMENT not in {"local", "test"}:
    raise ImproperlyConfigured("Only explicitly selected local/test environments are supported.")
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if len(SECRET_KEY) < 50 or "GENERATE_LOCALLY" in SECRET_KEY:
    raise ImproperlyConfigured("Provide a generated DJANGO_SECRET_KEY of at least 50 characters.")
DEBUG = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "api", "device-api", "testserver"]
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "rest_framework",
    "drf_spectacular",
    "sii.accounts",
    "sii.common",
    "sii.tenants",
    "sii.audit",
    "sii.assets",
    "sii.telemetry",
    "sii.monitoring",
    "sii.rules",
    "sii.incidents",
    "sii.notifications",
    "sii.reports",
    "sii.support",
    "sii.events",
    "sii.adapters",
    "sii.billing",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "sii.common.middleware.RequestIdMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
AUTH_USER_MODEL = "accounts.CustomUser"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "sii_local"),
        "USER": os.environ.get("POSTGRES_USER", "sii_local"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "postgres"),
        "PORT": "5432",
        "CONN_MAX_AGE": 0,
        "OPTIONS": {"connect_timeout": 3},
    }
}
# Migrations/tests retain the explicitly selected local schema owner. Running services
# authenticate as a separate non-owner, so SQL injection cannot disable evidence triggers.
# Development env_file still contains owner credentials; production secret separation is gated.
if ENVIRONMENT == "local" and os.environ.get("SII_DB_RUNTIME") == "1":
    DATABASES["default"]["USER"] = "sii_runtime"
    DATABASES["default"]["PASSWORD"] = os.environ.get("API_DB_PASSWORD", "")
    if len(DATABASES["default"]["PASSWORD"]) < 50:
        raise ImproperlyConfigured("Generate the runtime database credential with setup.")
USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("da", "Dansk")]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = []
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": f"django.contrib.auth.password_validation.{name}"}
    for name in [
        "UserAttributeSimilarityValidator",
        "MinimumLengthValidator",
        "CommonPasswordValidator",
        "NumericPasswordValidator",
    ]
]
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["sii.accounts.security.VerifiedSessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["sii.common.permissions.DenyAll"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "sii.common.errors.exception_handler",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}
SPECTACULAR_SETTINGS = {
    "ENUM_NAME_OVERRIDES": {
        "AssetLifecycle": "sii.assets.models.Lifecycle.choices",
        "PilotReviewKind": "sii.adapters.models.ReviewKind.choices",
        "BillingState": "sii.billing.models.SubscriptionState.choices",
        "BillingCurrency": "sii.billing.models.Currency.choices",
        "SupportTicketState": "sii.support.models.TicketStatus.choices",
    },
    "TITLE": "SAMSEL Industrial Intelligence — Foundation API",
    "VERSION": "0.1.0",
    "OAS_VERSION": "3.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_AUTHENTICATION": [],
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    "DESCRIPTION": "Local identity and tenant administration. No monitoring or device control.",
}
REDIS_URL = "redis://:" + quote(os.environ.get("REDIS_PASSWORD", ""), safe="") + "@redis:6379/0"
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}
}
CELERY_BROKER_URL = (
    "amqp://"
    + quote(os.environ.get("RABBITMQ_DEFAULT_USER", ""), safe="")
    + ":"
    + quote(os.environ.get("RABBITMQ_DEFAULT_PASS", ""), safe="")
    + "@rabbitmq:5672//"
)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_DEFAULT_QUEUE = "foundation"
CELERY_TASK_QUEUES = tuple(
    Queue(name, durable=True)
    for name in ["foundation", "ingestion", "rules", "reports", "notifications"]
)
CELERY_TASK_CREATE_MISSING_QUEUES = False
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_CONNECTION_TIMEOUT = 3
# RabbitMQ 4.3 rejects transient non-exclusive queues. Control/event queues are
# connection-local and ephemeral; actual task queues above remain durable.
CELERY_CONTROL_QUEUE_EXCLUSIVE = True
CELERY_EVENT_QUEUE_EXCLUSIVE = True
CELERY_WORKER_CANCEL_LONG_RUNNING_TASKS_ON_CONNECTION_LOSS = True
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp"
EMAIL_PORT = 1025
EMAIL_TIMEOUT = 5
# Auth links carry secrets only in URL fragments; never derive destinations from Host input.
PORTAL_ORIGIN = "http://127.0.0.1:5173"
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
DATA_UPLOAD_MAX_MEMORY_SIZE = 65536
CSRF_FAILURE_VIEW = "sii.common.errors.csrf_failure"
MFA_ENCRYPTION_KEY = os.environ.get("MFA_ENCRYPTION_KEY", "")
DEVICE_ENCRYPTION_KEY = os.environ.get("DEVICE_ENCRYPTION_KEY", "")
EVIDENCE_ENCRYPTION_KEY = os.environ.get("EVIDENCE_ENCRYPTION_KEY", "")
DEFAULT_FROM_EMAIL = "development@example.invalid"
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
}
