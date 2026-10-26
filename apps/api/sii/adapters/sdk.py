"""Transport-independent read-only SDK and durable local replay buffer.

Only the software simulator profile is registered. This interface is not a sandbox
or a vendor compatibility claim. A future plugin requires separate partner/site
qualification and network review. Spool files are trusted operator-owned local
files; never open uploaded SQLite files or store credentials in this buffer.
"""

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Profile:
    """Declare software capabilities; configuration cannot manufacture a real profile."""

    code: str = "sii-simulator-v1"
    read_only: bool = True
    synthetic: bool = True
    unit: str = "degC"
    expected_interval_sec: int = 60
    buffered_timestamps: bool = True

    def __post_init__(self):
        """Fail closed on write capabilities or a claimed unqualified real integration."""
        if not self.read_only or not self.synthetic or self.code != "sii-simulator-v1":
            raise ValueError("No authorised hardware profile registered")


SIMULATOR = Profile()


def utc(value):
    """Preserve an explicit source instant; never infer local time or repair a missing clock."""
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Explicit source timestamp offset required")
    return value.astimezone(UTC).isoformat()


@dataclass(frozen=True)
class Sample:
    """Read-only observation with a fictional engineering range, not a food-safety threshold."""

    sensor_id: uuid.UUID
    sequence: int
    observed_at: datetime
    value: Decimal
    unit: str = "degC"

    def event(self, gateway_id):
        """Create stable sensor/sequence identity, preserving the original value and clock."""
        sensor, gateway = uuid.UUID(str(self.sensor_id)), uuid.UUID(str(gateway_id))
        if type(self.sequence) is not int or not 0 <= self.sequence <= 9223372036854775807:
            raise ValueError("Invalid source sequence")
        value = Decimal(str(self.value))
        if (
            not value.is_finite()
            or not -100 <= value <= 150
            or value.as_tuple().exponent < -4
            or self.unit != SIMULATOR.unit
        ):
            raise ValueError("Unsupported simulator value/unit/precision")
        return {
            "version": 1,
            "event_id": str(uuid.uuid5(gateway, f"{sensor}:{self.sequence}")),
            "sensor_id": str(sensor),
            "sequence": self.sequence,
            "observed_at": utc(self.observed_at),
            "value": format(value, "f"),
            "unit": self.unit,
        }


class ReadOnlyAdapter(Protocol):
    """Adapter producers yield observations only; no command/write/control API exists."""

    profile: Profile

    def samples(self):
        """Yield source-clock Sample values; transport authentication belongs to the caller."""
        ...


class SyntheticAdapter:
    """Software-only producer for qualification tests; performs no equipment or network I/O."""

    profile = SIMULATOR

    def __init__(self, observations):
        """Accept a trusted iterable of synthetic observations without modifying them."""
        self.observations = observations

    def samples(self):
        """Yield supplied immutable samples, preserving gaps and out-of-order timestamps."""
        yield from self.observations


class ReplayBuffer:
    """Gateway-bound SQLite spool with FULL commits and application-receipt acknowledgments.

    The operator supplies a private persistent path. Reopen with the same gateway;
    conflicting source sequence data and wrong-gateway reuse fail before delivery.
    A transport must verify TLS/device authentication and the durable receipt before
    calling acknowledge; an MQTT broker PUBACK is insufficient.
    """

    def __init__(self, path, gateway_id):
        """Open/create a private versioned spool; close it if ownership validation fails."""
        self.gateway_id = uuid.UUID(str(gateway_id))
        self.db = sqlite3.connect(Path(path))
        try:
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS identity
                    (gateway TEXT PRIMARY KEY, profile TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS samples (id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                    delivered INTEGER NOT NULL DEFAULT 0, receipt TEXT);
                CREATE TABLE IF NOT EXISTS discontinuities (start TEXT, end TEXT, reason TEXT);
            """)
            identity = self.db.execute("SELECT gateway,profile FROM identity").fetchall()
            expected = (str(self.gateway_id), SIMULATOR.code)
            if identity and identity != [expected]:
                raise ValueError("Spool belongs to another gateway/profile")
            self.db.execute("INSERT OR IGNORE INTO identity VALUES (?,?)", expected)
            self.db.commit()
            # Credentials never enter SQLite; restrict the file as defense in depth.
            Path(path).chmod(0o600)
        except Exception:
            self.db.close()
            raise

    def enqueue(self, sample):
        """Persist before network I/O; accept identical retries and deny changed source data."""
        event = sample.event(self.gateway_id)
        payload = json.dumps(event, sort_keys=True, separators=(",", ":"))
        old = self.db.execute(
            "SELECT payload FROM samples WHERE id=?", [event["event_id"]]
        ).fetchone()
        if old and old[0] != payload:
            raise ValueError("Source sequence conflict")
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO samples(id,payload) VALUES (?,?)",
                [event["event_id"], payload],
            )
        return event["event_id"]

    def pending(self, limit=100):
        """Return a bounded oldest-insertion batch; no observations are invented across gaps."""
        if not 1 <= limit <= 1000:
            raise ValueError("Batch limit is 1..1000")
        return [
            json.loads(row[0])
            for row in self.db.execute(
                "SELECT payload FROM samples WHERE delivered=0 ORDER BY rowid LIMIT ?", [limit]
            )
        ]

    def acknowledge(self, event_id, receipt):
        """Mark delivery only from a durable accepted/duplicate application receipt."""
        if receipt.get("status") not in {"accepted", "duplicate"}:
            raise ValueError("Durable application receipt required")
        reading = str(uuid.UUID(str(receipt.get("reading_id"))))
        row = self.db.execute("SELECT receipt FROM samples WHERE id=?", [str(event_id)]).fetchone()
        if row is None or (row[0] and row[0] != reading):
            raise ValueError("Unknown event or conflicting receipt")
        with self.db:
            self.db.execute(
                "UPDATE samples SET delivered=1,receipt=? WHERE id=?", [reading, str(event_id)]
            )

    def discontinuity(self, start, end, reason="network_unavailable"):
        """Record known outages separately; absence never becomes a zero or healthy reading."""
        if not timedelta(0) < end - start <= timedelta(days=7) or reason not in {
            "network_unavailable",
            "producer_restart",
        }:
            raise ValueError("Invalid discontinuity")
        with self.db:
            self.db.execute(
                "INSERT INTO discontinuities VALUES (?,?,?)", [utc(start), utc(end), reason]
            )

    def close(self):
        """Release the local connection; committed pending records survive process restart."""
        self.db.close()

    def __enter__(self):
        """Return the open operator-owned spool for a bounded operation."""
        return self

    def __exit__(self, *_):
        """Close on success/failure without deleting any accepted or pending observation."""
        self.close()


def manifest():
    """Expose only the qualified software fixture; no supplier approvals are inferred."""
    return asdict(SIMULATOR)
