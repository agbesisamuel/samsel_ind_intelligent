# Architecture decisions

## ADR-001 — Sprint 01 foundation (2026-10-20)

Accepted: modular Django/DRF API, React/TypeScript/Vite SPA, PostgreSQL, RabbitMQ/Celery, Redis, local MinIO and Mailpit. Exact resolved dependencies will be recorded in lock files and docs/DEPENDENCIES.md after installation. Choose supported stable releases; Django 5.2 LTS and Node 24 LTS are the intended lines. No production infrastructure is provisioned.

Initial disposition: MinIO was explicitly requested but its community repository is archived (https://github.com/minio/minio). An isolated local source build temporarily left SEC-05 unresolved. **Superseded by ADR-006** following the user's explicit request to resolve that exception.

## ADR-002 — Fail closed until identity and tenancy exist

CustomUser is created before the first migration, with UUID identity and database-enforced case-insensitive email uniqueness. No login, signup, Django admin or business API is exposed. Default DRF permission denies every principal, including staff. Only explicitly public, data-free infrastructure probes and local schema are available. Tenant/site authorization and MFA belong to Sprint 02; no frontend state confers authority.

## ADR-003 — Local development only

Compose services have project-scoped volumes and isolated internal infrastructure; published UI/API ports bind loopback. A cross-platform Python runner backs every Make target, generates unique local secrets without printing them, and refuses non-local operation. Startup migrates automatically, while explicit migrate remains idempotent. No production settings are provided: unknown/non-local environment refuses startup until later deployment work.

## ADR-004 — Generated contract ownership

Django view serializers generate OpenAPI 3.1; openapi-typescript generates the committed TS contract. Regenerate both with the documented contracts command; never hand-edit generated files. CI checks drift. Forms, charts and domain modules are introduced only when their scheduled sprint requires them.

The API runs as a non-root container UID. Schema regeneration writes into `/tmp`
and copies out via Compose so Linux host-file ownership cannot block generation.
Ruff commands disable their write cache for the same source-mount portability reason.

## ADR-005 — Celery compatibility with supported RabbitMQ

RabbitMQ 4.3 rejects transient non-exclusive queues. Celery 5.6.3 supports explicit
exclusive control/event queues, so enable those for ephemeral worker inspection
and gossip. Domain task queues remain durable. Do not re-enable RabbitMQ's
deprecated queue feature or downgrade to an unsupported broker. Stack smoke
requires a real worker response. See [Celery configuration](https://docs.celeryq.dev/en/stable/userguide/configuration.html)
and [RabbitMQ queues](https://www.rabbitmq.com/docs/queues).

## ADR-006 — Resolve archived MinIO support (2026-10-21)

Accepted for Sprint 01 local development: replace MinIO with **SeaweedFS 4.48**,
the current stable upstream release, Apache-2.0, pinned to the official project's
`chrislusf/seaweedfs` image manifest digest
`sha256:4e61d15fd35994cb1e43e1e553dff106794841fd9a99ade2fc8c8bfce4d7872d`.
This supersedes only ADR-001's MinIO choice under the user's follow-up instruction;
the master specification remains unchanged. It removes the unsupported component
instead of accepting its risk or purchasing a commercial contract. Active community
maintenance is the support basis, not a contractual SLA or LTS promise.

Use one `weed server` process with master/filer/volume bound to container loopback
and a dedicated internal storage network. A non-root, read-only **nginx 1.30.6**
S3-only proxy exposes `object-store:8333` on the application private network.
This extra service is necessary because SeaweedFS also binds its S3 gRPC control
listener (18333) to the S3 address; application containers cannot resolve/reach
the backend or that control port. The proxy preserves signed Host/URI and resolves
Docker DNS dynamically across backend recreation. No host ports,
WebDAV, admin UI, IAM management, Iceberg/Lance catalogs or telemetry are enabled.
No automatic bucket creation or recursive bucket deletion. Run non-root with a
read-only root filesystem, dropped capabilities, temporary private credential config
and a new persistent volume. Startup rejects non-local mode and invalid credentials.
The healthcheck authenticates; smoke also verifies anonymous/invalid rejection,
unreachable internal ports and a unique synthetic object lifecycle with cleanup.

No tenant adapter, report bucket, browser access or domain storage workflow is
introduced. The local administrative credential is infrastructure-only; scoped
tenant credentials and authorization remain later work. The old `sii-local_minio-data`
volume and legacy `.env` keys are preserved, never mounted into SeaweedFS or migrated.
There are no Sprint 01 domain objects to migrate. Inspect/backup any independently
added data before a separate migration. Production deployment remains out of scope.

Evidence: [stable release](https://github.com/seaweedfs/seaweedfs/releases/tag/4.48),
[licence](https://github.com/seaweedfs/seaweedfs/blob/4.48/LICENSE),
[versioned server flags](https://github.com/seaweedfs/seaweedfs/blob/4.48/weed/command/server.go),
[S3 credentials](https://github.com/seaweedfs/seaweedfs/wiki/S3-Credentials),
[nginx stable release](https://nginx.org/en/download.html),
and `SPRINT_01_STORAGE_VERIFICATION.md` for executed checks.

## ADR-007 — Invite-only identity and explicit tenancy (2026-10-21)

Accepted Sprint 02. Django server-side sessions and CSRF protect the same-origin
portal. New accounts require a 48-hour invitation email proof. Existing accounts
cannot have passwords or MFA replaced by an invitation. Password resets expire
in 30 minutes, are single-use and revoke sessions without removing MFA. Password
hashes use Django's configured PBKDF2 in local runtime; test-only MD5 accelerates
fixtures and is never selected by local runtime.

Owner, site administrator, QA and platform staff require TOTP. Optional enrollment
is available to other users. PyOTP 2.10.0 checks TOTP; cryptography 50.0.2 Fernet
protects seeds with a separate generated 256-bit key. Lock each user while consuming
a counter; accept at most ±1 time step and never reuse a counter. The initial
49.0.0 constraint was rejected by audit (PYSEC-2026-3552), then replaced with the
current stable fixed release. Raw random invite/reset/recovery tokens are stored
only as SHA-256 hashes. Recovery requires prior password proof, consumes the code,
revokes existing sessions and all old codes, then mandates new factor enrollment.
There is no email-only MFA removal or hidden staff bypass. Losing all proofs needs
a separately reviewed human identity-recovery procedure before production.

Every tenant entity has immutable direct organisation ownership. Model validation
and PostgreSQL triggers/composite FKs protect ordinary and bulk writes. Membership
alone grants nothing. Only owner is organisation-wide; every other role is bound
to one site. Recompute active grants on requests and in reusable service scopes.
Platform superuser provisions/lists metadata but cannot read sites or customer
records without an ordinary explicit grant. No support bypass exists (AUTH-03 is
Sprint 10). Unknown/foreign IDs share 404 behavior. Secure cookie settings remain
on in base settings; local loopback HTTP overrides are explicit.

Sensitive edits require password and unused TOTP within five minutes. Session
assurance is rechecked after role elevation and auth-version changes. A per-org
lock serializes role removal/deactivation to retain an owner. Audit records contain
identifiers and before/after hashes, never secrets or raw payload snapshots. A
per-organisation head serializes an SHA-256 chain. PostgreSQL rejects audit UPDATE
and DELETE. This is append-only application evidence, **not immutable against the
database owner**; external anchoring, restricted DB roles and production backups
remain Sprint 10. Audit reads are scoped; global auth events are not exposed to tenants.

Local reset requests queue identical known/unknown jobs so HTTP does not reveal
account existence through SMTP timing. Celery is initialized in config/__init__
for all Django and worker entrypoints; auth-smoke verifies the actual route through
RabbitMQ and Mailpit. Account email failures are audited; guaranteed delivery and
notification outbox/DLQ remain Sprint 07. No customer alert is sent.

The small identity/admin forms use native labelled HTML controls and server-side
validation, avoiding a new form library until more complex workflows justify it.
English and Danish copies are complete. Client role visibility is only a hint;
permissions always come from current server scope. Browser storage holds language
preference only. Secrets remain in component memory; link fragments are cleared.

Sources: [PyOTP security guidance](https://pyauth.github.io/pyotp/),
[cryptography changelog](https://cryptography.io/en/stable/changelog/),
[cryptography stable metadata](https://pypi.org/project/cryptography/),
[Django authentication](https://docs.djangoproject.com/en/5.2/topics/auth/default/).

## ADR-008 — Preserved qualification with fail-closed activation (2026-10-21)

Sprint 03 adds a site-anchored facility/device tree with PostgreSQL triple-key FKs
and immutable identity anchors. Device reassignment needs a future explicit audited
transfer protocol; ordinary metadata edits cannot move devices. Archive buildings/
zones and retire devices to preserve historical references. Calibration, placement,
site-pack, test and acceptance records are append-only at the DB boundary. Each
amendment is a new record. QA acceptance stores the normalized evidence snapshot
and digest and recalculates whether it still matches current configuration.

All local evidence is synthetic and server-marked. Neither an input flag nor staff
status can turn it into real qualification. Calibration metadata and zone category
never choose food-safety thresholds. Exact site QA authority is separate from
owner/site administration. A complete local pack supports testing the workflow,
not actual site activation. Active device/site monitoring remains blocked pending
implemented approved rules, verified routes and real customer/QA/site authorization.
No compatibility, calibration or pilot sign-off is invented. One-time credential
provisioning is designed here and implemented/enforced in Sprint 04.

## ADR-010 — Independent freshness and explicit timing approval (2026-10-21)

A separate watcher evaluates timestamps even when ingestion is silent. QA approval
snapshots cadence and bounded sensor/gateway timeouts; changing cadence invalidates
approval currency. Observation/receipt clocks and gateway health are distinct.
No-data, missing policy, unqualified devices and delayed watchers cannot appear fresh.
UTC-hour aggregation preserves DST folds and empty buckets; raw inspection is bounded
and shares the exact query window. CSV preview uses the domain validator without
writes and commit always revalidates. See MONITORING.md for limits and provenance.
ADR-009 is maintained in adr/009-durable-telemetry.md.

## ADR-011 — Immutable rules and separate recovery evidence (2026-10-21)

One temperature family per zone avoids conflicting precedence. Immutable versions,
previews, QA approvals and immediate activation boundaries preserve governing
configuration. QA approval binds qualification and timing; ownership cannot approve.
A pure event-time machine handles duration, completeness, hysteresis and gaps.
Gateway locks serialize incident creation; evaluation and outbox completion commit
together. Recovery preserves open human work. Backfill/superseded input cannot
rewrite live history. Maintenance remains visible and expires. See RULES.md.

## ADR-012 — Durable notification intents and uncertain SMTP outcomes (2026-10-21)

Persist scheduling and per-recipient intents before sending. Recheck exact scope,
consent and grants; store immutable outcomes with bounded retries. SMTP acceptance
is not acknowledgement. Ambiguous sends/lost leases become uncertain rather than
automatic duplicates. Contingency is explicit/nonrecursive; missing routes and
failures remain visible. Expired maintenance reconsiders pending work. Only TEST
Mailpit capture is enabled. See NOTIFICATIONS.md.

## ADR-013 — Human closure and constrained encrypted evidence (2026-10-21)

Human response is a validated revisioned state machine with replay-safe immutable
events, independent QA/MFA and observed recovery before closure. Gateway-first locks
serialize renewed breaches with QA actions; recurrence invalidates prior review.
Only bounded UTF-8 plain text attachments are enabled. No unsafe document parser or
unverified malware scanner is introduced. Encrypt before private S3, authenticate
scope/checksum on download, and retain audited metadata. See INCIDENT_WORKFLOW.md.

## ADR-014/015 — Reports and local hardening (2026-10-21)

Bounded immutable reports: adr/014-bounded-evidence-reports.md. Scoped support,
16 fixed gateway shards, restricted runtime SQL, encrypted isolated recovery and
explicit production gates: adr/015-local-security-performance-recovery.md.

## ADR-016 — No invented hardware qualification

Only sii-simulator-v1 is registered. Source clocks/units/sequence and disconnected
replay are explicit SDK contracts; a verified application receipt precedes spool
ACK. Synthetic review snapshots are immutable and cannot flip live authorization.
Actual profiles/installation need partner/customer authorization and qualification.
See ADAPTER_SDK.md and PILOT_CHECKLIST.md.

## ADR-017 — Expansion quotas and local manual finance

Use immutable technical templates, organisation-default subscriptions and SQL quota
guards serialized on the subscription row. Count planned/non-retired probes and
use wall time after locks for expiry. Commercial terms constrain new capacity only,
never existing monitoring or incident evidence; preserve assets on downgrade.
Explicit platform commercial metadata authority grants no site access. Current
owner scope guards exports; recent MFA guards changes/drafts. No provider, automatic
tax/pricing or collections. Internal immutable support never sends externally or
closes incidents. See COMMERCIAL.md, OPERATIONS.md and RELEASE_REVIEW.md.

Sprint 12 performance follow-up: two ingress Gunicorn processes could not sustain
the repeat reference cadence on this shared local host, classifying 978 queued
source observations as late backfill. Increase only device-api to four processes;
retain gateway locks, qualification and late-data exclusion. The reference command
now gates sender duration (three minutes plus 30 seconds) and zero late readings as
well as durable counts/processing/dashboard/TEST notification outcomes. Preserve
failed measurements and do not reinterpret an overloaded sender as a passed load.
