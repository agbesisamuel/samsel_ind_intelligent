"""Independently verify hash chains; external checkpoints detect privileged truncation."""

from .models import AuditEvent, AuditHead
from .services import digest


def verify():
    """Return non-secret chain heads or raise on mutation, missing sequence or head mismatch.

    A database owner can rewrite all evidence; compare the returned checkpoint with
    the separately encrypted backup/export held outside that database as well.
    """
    result = []
    for head in AuditHead.objects.order_by("key"):
        query = AuditEvent.objects.filter(
            organisation_id=None if head.key == "global" else head.key
        )
        previous, sequence = "", 0
        # Concurrent appends after this head read are not part of this checkpoint.
        for item in (
            query.filter(sequence__lte=head.sequence).order_by("sequence").iterator(chunk_size=500)
        ):
            fields = {
                name: getattr(item, name)
                for name in [
                    "organisation_id",
                    "site_id",
                    "actor_id",
                    "action",
                    "subject",
                    "occurred_at",
                    "sequence",
                    "before_hash",
                    "after_hash",
                    "prev_hash",
                ]
            }
            if (
                item.sequence != sequence + 1
                or item.prev_hash != previous
                or digest(fields) != item.event_hash
            ):
                raise ValueError("Audit chain integrity failure")
            previous, sequence = item.event_hash, item.sequence
        if (head.sequence, head.event_hash) != (sequence, previous):
            raise ValueError("Audit head mismatch")
        result.append({"chain": head.key, "sequence": sequence, "hash": previous})
    return result
