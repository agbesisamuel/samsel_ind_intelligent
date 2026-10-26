"""Local Celery bootstrap for synthetic jobs; device ingestion has a separate durable consumer."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
app = Celery("sii")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
