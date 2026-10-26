"""Email provider boundary. Only the local capture adapter is enabled in this build."""

import os
import smtplib

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage


class DeliveryFailure(Exception):
    """Safe error classification only; never retain provider exception text or email bodies."""

    def __init__(self, uncertain=False):
        """Classify ambiguous SMTP disconnects as unsafe to retry automatically."""
        self.uncertain = uncertain
        super().__init__("delivery_uncertain" if uncertain else "provider_unavailable")


def deliver(address, subject, body, key):
    """Return a stable local acceptance reference, not delivery/read/acknowledgement proof.

    Provider selection is environment-owned. Unsupported production adapters fail
    closed; no fallback to internet SMTP or paid sends exists. The capture sink has
    no relay. A production adapter must supply tested idempotency and secret wiring.
    """
    if (
        settings.ENVIRONMENT not in {"local", "test"}
        or os.environ.get("NOTIFICATION_PROVIDER", "local_capture") != "local_capture"
        or settings.EMAIL_HOST != "smtp"
    ):
        raise ImproperlyConfigured("Only local capture notifications are enabled.")
    message = EmailMessage(
        "[TEST] " + subject,
        "SYNTHETIC DEVELOPMENT — no real site alert.\n" + body,
        settings.DEFAULT_FROM_EMAIL,
        [address],
        headers={"Message-ID": f"<{key}@notifications.example.invalid>"},
    )
    try:
        if message.send(fail_silently=False) != 1:
            raise DeliveryFailure()
    except (TimeoutError, smtplib.SMTPServerDisconnected) as exc:
        raise DeliveryFailure(uncertain=True) from exc
    except (OSError, smtplib.SMTPException) as exc:
        raise DeliveryFailure() from exc
    return str(key)
