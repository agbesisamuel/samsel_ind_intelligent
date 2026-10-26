"""Bind shared tasks to the configured broker in Django, workers and standalone commands."""

from .celery import app as celery_app

__all__ = ("celery_app",)
