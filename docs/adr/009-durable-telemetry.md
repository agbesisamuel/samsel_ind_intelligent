# ADR-009: Separate device transport, durable evidence and synthetic provenance

Status: accepted for local synthetic development, 2026-10-21.

Use the existing RabbitMQ 4.3.6 MQTT plugin and separate vhost instead of adding a
second broker. Devices have expiring per-gateway credentials, exact publish-only
topic ACLs and application HMAC verification. A dedicated TLS-only HTTP listener
has no human routes. Both transports call one domain validator.

Commit accepted measurements and processing outbox together in PostgreSQL. Preserve
raw normalized contract/provenance separately from mutable delivery state. Broker
PUBACK is explicitly distinguished from application persistence. Duplicate UUIDs
and sequences cannot create new measurements; buffered out-of-order values retain
both clocks. Quarantine metadata excludes arbitrary rejected payload bodies.

Use the existing cryptography dependency for a strict development CA and encrypted
device secrets. Add Paho MQTT 2.1.0 solely for the synthetic gateway. Its in-memory
session is not a durable offline store; a named-volume SQLite spool owns unsent
events. No gateway hardware compatibility or actual calibration is implied.

Production still requires managed certificate/key lifecycle, least-privilege service
identities/DB roles, storage retention/quotas, external security review and authorized
device/site qualification. A local test pass cannot enable a monitored customer site.
