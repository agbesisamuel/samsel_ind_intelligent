"""Dedicated TLS ingestion WSGI entrypoint; settings expose device routes only."""

import os

from django.core.wsgi import get_wsgi_application

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.device"
application = get_wsgi_application()
