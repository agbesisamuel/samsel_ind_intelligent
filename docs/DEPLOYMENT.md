# Development stack and deployment boundary

Only local synthetic development is supported. Settings refuse any environment
other than local/test. This repository has no production deployment or approvals.
Do not expose this Compose stack to the internet or put customer data into it.

The independent notification-worker polls durable intents every five seconds and
expires its health heartbeat after 90 seconds. Long-running services
remain private or loopback only. Wait for health after recreation before browser
checks: `docker compose up -d --no-deps --wait api notification-worker`. TEST delivery
drill: `python scripts/dev.py notification-smoke`. See NOTIFICATIONS.md for uncertain
SMTP handling, local-only provider boundary and preserved failure evidence.

API/worker use the same image and PostgreSQL schema. Migration runs once before
they start. PostgreSQL, durable RabbitMQ, persistent Redis and SeaweedFS use named
project volumes. Cache is never the sole business persistence layer. The internal
network isolates infrastructure; the API/frontend and Mailpit UI have loopback
ports. SeaweedFS exposes only authenticated S3 on the internal network at
`http://object-store:8333` (path-style requests, signing region `us-east-1`).
The nginx S3-only proxy shares a dedicated internal network with the backend;
the API has no route/DNS entry to the backend's S3 gRPC control listener. Master,
filer and volume endpoints bind container loopback; optional interfaces are disabled.
The proxy caps local requests at 16 MiB; larger/multipart/report workflows require
explicit implementation and validation. The private application bucket now holds
scope-bound encrypted evidence and report artifacts (Sprints 08/09). The smoke
command creates a uniquely named `sii-smoke-*` bucket and synthetic object, then
deletes them. Interrupted cleanup can leave synthetic artifacts; never bulk-delete
unknown buckets. Healthchecks only perform an authenticated bucket-list request.

Run `setup` on an existing checkout to append new `S3_ACCESS_KEY`/`S3_SECRET_KEY`
without rotating other credentials. Then run
`docker compose up --build -d --remove-orphans --wait` to retire the old MinIO
container. `sii-local_minio-data` and legacy `.env` entries remain untouched for
recovery; they are not compatible with the new `sii-local_object-store-data` format.
Never reuse that old volume for SeaweedFS. No automatic data migration occurs.
New keys must be 64 lowercase hex characters. The entrypoint regenerates a
mode-0600 config on tmpfs at startup, so explicit key rotation requires recreating
the container with `up`. It never falls back to unauthenticated mode.

`make down` preserves volumes. Reset-demo does not flush databases or remove
volumes; Sprint 02 retains synthetic identities and audit evidence. Never run destructive volume
cleanup against unknown data. Initial CustomUser migration is Django-generated
and reversible before dependent business schemas exist. Reversing it drops user
records; do not use reversal on customer data. Roll back code/images only with
schema compatibility review and a backup when data exists.

Later release gates: production storage architecture and least-privilege credentials,
TLS/secure cookies, EU hosting, secrets manager, encrypted backups, verified
restore, worker DLQ/replay/idempotency, monitoring, security/legal/site acceptance.
Sprint 10 demonstrates isolated local restore timing; uptime and production
readiness still require the release gates in THREAT_MODEL.md and RECOVERY.md.

Sprint 02 upgrade: run setup to append MFA_ENCRYPTION_KEY and unique demo credentials,
then up/migrate/seed-demo. Preserve the MFA encryption key with the local secret
backup; losing it makes enrolled seeds unreadable. Do not rotate it by replacing
.env without a reviewed re-encryption procedure. New generated model migrations
and the explicit scope/audit guard migration depend on PostgreSQL. Reversing guards
removes protection; reversing model migrations deletes security/tenant evidence.
Do not reverse these against customer data. No destructive reset is provided.


Sprint 03 migration warning: assets/0001 creates scoped inventory/evidence;
0002 installs hand-authored triple-key foreign keys and append-only/identity
triggers; 0003 adds the immutable normalized QA evidence snapshot. Reversing the
schema drops qualification evidence; reversing guards removes protection. Preserve
backup/schema compatibility and never use reversal as an operational cleanup.

## Sprint 04 local transport

Compose adds TLS-init and telemetry-bootstrap one-shots, device-api and a durable
telemetry-worker (eleven long-running services total). Loopback ports 8443 HTTPS
and 8883 MQTT are added; plaintext MQTT and broker management are not published.
`setup` appends DEVICE_ENCRYPTION_KEY without rotating existing secrets. Preserve
this key with the database in any reviewed backup. TLS public/private v2 and
simulator-data volumes survive `down`; initial v1 certificate volumes remain
unmounted for inspection. Never use down -v as an upgrade/rollback procedure.
Rollback must preserve telemetry, audit and outbox evidence; do not reverse the
append-only SQL migration. Local certificate expiry is a deliberate startup failure;
use a reviewed new-volume certificate rotation. No host trust installation occurs.

## Sprint 05 watcher

The independent freshness-worker adds a twelfth long-running service. Its heartbeat
fails after 60 seconds without a complete scan; the API independently invalidates
stale projections. Run `docker compose exec -T api python manage.py watch_freshness
--once` for a local one-shot check. Rebuild projections from immutable raw records;
never alter raw observations to repair a dashboard. QA policy approval is required;
no fixture automatically grants a real site's timing or threshold approval.

Sprint 12 handover/rollback: OPERATIONS.md; manual commercial controls: COMMERCIAL.md;
human go/no-go: RELEASE_REVIEW.md. Billing catalog/default/quota and immutable support
guards remain in place. migrate revokes runtime plan DML. No production configuration,
automatic promotion or live collections is supplied. Never recreate API during a
pytest exec session. Generated artifacts belong to their documented generators.
