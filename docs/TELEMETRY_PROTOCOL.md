# Synthetic telemetry protocol v1

This local implementation is read-only. It sends no device/PLC/control commands.
Its range `-100..150 degC` belongs only to the fictional simulator profile; it is
neither a physical device capability claim nor a customer food-safety threshold.

Device HTTPS is a separate Gunicorn listener on `https://127.0.0.1:8443` with only
`POST /api/v1/device/ingest/` and `GET /api/v1/device/receipts/{event_id}/`.
Human administration remains on the development HTTP API. Human cookies do not
authenticate devices; device secrets do not authenticate human administration.
Forwarded protocol headers cannot convert HTTP into an authenticated TLS request.

Device authorization is `Authorization: Device <credential UUID>.<one-time secret>`.
Owners/site administrators issue expiring (1–90 day) credentials for an exact
gateway after fresh MFA. Rotation issues a new credential, updates the gateway,
then revokes the previous one. Secret values are returned only once; the separate
DEVICE_ENCRYPTION_KEY encrypts signing secrets at rest. Revocation commits before
broker deletion, and failed broker cleanup returns 503 for explicit retry. Pending
provisioning cannot authenticate. No default/shared device password exists.

The exact JSON event fields are:

| Field | Contract |
|---|---|
| version | integer 1 |
| event_id | UUID, unique across one gateway |
| sensor_id | UUID assigned to the authenticated gateway and exact tenant/site |
| sequence | integer 0..9223372036854775807, unique per sensor |
| observed_at | ISO 8601 timestamp with explicit UTC offset |
| value | finite decimal, at most four fractional places |
| unit | `degC`, matching registered sensor |

Unknown fields, tenant selectors, unknown/retired/unqualified devices, wrong units,
out-of-capability-range values, timestamps older than seven days or over five
minutes ahead are rejected. Current calibration and read-only placement evidence,
commissioning state and capability reference/range are required. Server-assigned
source is always `simulator` in this environment, or `manual_import` for CSV.
Future skew over 30 seconds and samples older than twice the expected interval
receive explicit quality flags. This is ingestion validation, not rule evaluation.

HTTPS accepts one event or 1–100 events, at most 64 KiB. Each accepted response
maps to a committed append-only measurement **and** a transactional processing
outbox. A batch may contain mixed receipts; it is not all-or-nothing. Exact replay
returns the original measurement ID; conflicting UUID/sequence reuse is rejected.
Unique lower sequences are accepted as out-of-order backfill. Observation and
first application receipt timestamps are preserved independently. Backfill/manual
data does not pretend the gateway is currently online.

MQTT uses RabbitMQ's bundled plugin, TLS on loopback port 8883, no plaintext MQTT
listener, anonymous login disabled, separate `telemetry` vhost. Broker username is
`gw_<credential UUID without hyphens>`, password is the device secret. Publish QoS 1
to `ingest/<credential UUID without hyphens>`; no subscriptions/configuration are
granted. Exact topic permission is installed before resource permission. Payload:
`{"event": <event>, "signature": <hex HMAC-SHA256>}`. Sign the event's UTF-8 JSON
with sorted keys, compact separators, no NaN/Infinity. This application signature
also guards against protocol-level topic-ACL bypass. Maximum packet is 64 KiB.

**MQTT PUBACK is a broker receipt, not application acceptance.** Query the HTTPS
receipt endpoint before removing a buffered event. The proprietary consumer ACKs
only after a measurement or rejection record commits. A rejection retains reason,
digest, byte count and gateway scope, never arbitrary untrusted body text. Unknown
credentials and malformed routing go to the private broker dead-letter queue.

Quorum ingress/work/dead queues are durable. The outbox publisher uses confirms;
its crash window may redeliver, and processing is idempotent. Unprocessed outbox
records retry up to five publishes with bounded exponential delays, then remain
visible as dead letters. `telemetry_worker replay --confirm-local --limit 50`
requeues at most 100 dead outbox records belonging to fictional organisations.
Broker dead letters are retained for investigation; never purge them to fix a test.

Local CA/server keys live in dedicated named volumes. TLS fixture initialization
has no network and discards the CA private key. Leaf keys are restricted to their
service UID; only CA public material is used by clients. Strict certificate and
hostname validation remains enabled. Certificates expire after 90 days; existing
material is preserved and expired/partial fixtures fail closed. Renewal requires
an explicit reviewed fixture rotation, not turning off verification. No host trust
store is changed. These are development certificates, not production PKI.

`make telemetry-smoke` (or `python scripts/dev.py telemetry-smoke`) runs 1,000
events across both transports, malformed inputs, 100 duplicate attempts and a
foreign-topic broker rejection. Seed 42 defines normal/warm/cold/jitter/zero/gap/
out-of-order scenarios. The reserved simulator probe is separate from the original
unqualified demo probe. Before sending, events are committed to a FULL-synchronous
SQLite spool on `simulator-data`; it is reopened before replay. Credentials stay
in memory, never in the spool. Failed runs retain undelivered rows for investigation.
Spools are synthetic evidence and remain until explicitly reviewed for deletion.

Human endpoints under an authorized organisation/site:
`device-credentials/`, `device-credentials/{id}/revoke/`, `readings/`,
`ingestion-metrics/`, `csv-import/`. Metrics include accepted/pending/dead counts and
rejection reasons. They are not public Prometheus labels or safety status.
CSV requires explicit timezone/unit, at most 100 rows, manager MFA and same-site
credential. Sprint 05 adds unique column mapping, stable import IDs and the same
domain validation in preview/commit. Preview has no measurement/quarantine writes;
commit rechecks current constraints and returns each row's result. Source remains
permanently manual/imported. See MONITORING.md for the complete workflow.

Regenerate human/device OpenAPI and TypeScript with `make contracts`. Generated
files are owned by drf-spectacular/openapi-typescript, not manually edited.
