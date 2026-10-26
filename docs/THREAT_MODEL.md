# Sprint 10 threat model and privilege review

Reviewed 2026-10-21. This is a local synthetic development assessment, not an
external penetration test, legal approval or production deployment approval.

## Assets and boundaries

Protect tenant identities, MFA/device keys, raw measurements, approval/incident
history, private attachments/reports, audit checkpoints and backups. Untrusted
boundaries are browser input, device payloads, broker messages, imported text,
object ciphertext and support staff. The host/Docker administrator and migration
database owner remain trusted infrastructure operators. An application RCE with
development `.env` access exceeds the SQL-only runtime-role boundary; production
must use distinct per-service secret mounts and identities.

| Actor/path | Enforced authority | Residual threat / release gate |
|---|---|---|
| Anonymous browser | Invite/reset proof only; generic responses and throttles | External auth abuse and session testing |
| Member/operator/auditor | Current active exact-site grants on every request/download | Independent object-ID and export penetration test |
| Owner/site admin | Scoped configuration; explicit QA remains separate | Customer role review and joiner/leaver process |
| QA | Site assignment, current evidence, recent MFA for sensitive actions | Qualified human sign-off, never software food-safety certification |
| Platform staff | No customer membership bypass | Separate approved, expiring diagnostic session below |
| Device | TLS and gateway-specific credential/topic; exact persisted sensor scope | Production PKI, key rotation and partner qualification |
| Queue consumer | Complete envelope comparison to immutable scoped source | Broker administrator trusted; production per-service ACL review |
| API/worker SQL | `sii_runtime`, no superuser/DDL/role creation; protected audit triggers | Owner credentials still available in local development env |
| Migration/backup operator | Fixed local owner or isolated restore database | Production least-privilege backup/PITR identity and key custody |
| Object storage | Private network/proxy, encrypted scope-bound authenticated objects | Production KMS, lifecycle/retention and recovery custody review |

## Abuse cases and implemented defenses

Cross-tenant IDs fail at scoped query resolution and composite PostgreSQL keys.
Changes to memberships revoke access immediately. Staff flags grant no site access.
Unknown input fields, oversized uploads, arbitrary URLs, mutable ownership and
unsafe document formats are rejected. API CSP/frame/no-store headers and session
CSRF protect the browser boundary; tokens are not placed in browser local storage.

Replays are idempotent by persisted source identity; outbox insertion shares the
measurement transaction. Gateway-sharded consumers preserve serial processing.
Late/backfilled data cannot rewind live cursors. Independent freshness, notification
and report processes expose missed heartbeats/failures instead of inferring health
from silence. A provider receipt never acknowledges a human incident.

Audit rows are append-only to the runtime role and independently hash-verified.
An encrypted backup carries an earlier checkpoint checked against the restored
prefix. A database owner can rewrite an entire unanchored chain; external immutable
checkpoint custody remains a production gate, not a claimed cryptographic guarantee.

## Scoped support

An organisation owner with recent MFA may grant a different active verified staff
user a **diagnostics-only** session for 1–60 minutes, exact organisation/site, with
a recorded reason. Immutable approval fields cannot be extended or repointed.
Every diagnostic read checks current staff status, expiry, revocation, original
owner authority and recent MFA, then appends access and audit records. Revoke and
read serialize on the session row. Owners can read scoped access logs.

Only aggregate unresolved-incident, failed-notification and failed-report counts
are returned. This grant provides no raw measurements, files, membership, remote
shell, device action or ordinary API bypass. Tests cover expiry, revocation, owner
authority loss, self-approval denial, random/foreign identifiers and raw SQL guards.

## Production fail-closed policy

The shipped settings reject a production environment. Browser HTTP is loopback-only
development; the device surface uses a dedicated local CA and TLS. No proxy-header
trust is enabled to turn arbitrary requests into secure requests. Production must
provide reviewed HTTPS termination, secure/HttpOnly/SameSite cookies, CSRF origins,
explicit CORS allowlist (currently no cross-origin access), HSTS after validation,
secret manager, per-service networking, monitoring and external alert delivery.
`check --deploy` against local settings is not a production-policy verification.

## Release review and incident response

External security reviewer: test auth recovery/MFA replay, CSRF, role revocation,
concurrent support revoke, malformed envelopes, upload limits, object binding,
worker retry/crash, report expiry and tenant-ID fuzzing. Retain reproducible
evidence and resolve exploitable high/critical findings before release. The image
scan register must distinguish available fixes, unreachable code and unresolved
findings; never suppress by severity alone.

On suspected compromise: preserve volumes/logs, restrict exposed ingress, revoke
affected credentials/sessions, record scope and times, verify audit checkpoints,
restore into an isolated environment and reconcile evidence before resumption.
Contact customer/authority only through separately approved human procedures.
Never erase incident history or claim safety because notifications stopped.
