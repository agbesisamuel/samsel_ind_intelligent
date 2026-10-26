# SAMSEL Industrial Intelligence

The local stack includes synthetic ingestion, freshness, approved rule versions and
TEST notification delivery. After `setup`, `up` and `seed-demo`, run
`python scripts/dev.py telemetry-smoke` and `python scripts/dev.py notification-smoke`.
Device TLS endpoints use loopback
8443/8883 and a private local CA; see [protocol and recovery semantics](docs/TELEMETRY_PROTOCOL.md).
Passing synthetic tests does not activate real monitoring or authorize hardware.

Local Sprints 01–12 software for the proprietary SAMSEL platform.
The master implementation specification is the source of truth. This release
implements invite-only login, exact tenant/site permissions, audit, inventory and
synthetic commissioning. `/readings`, `/rules` and `/notifications` expose scoped
observation, version approval and local delivery evidence. Human incident workflow,
reports, scoped support and commercial work are tracked in [implementation status](docs/IMPLEMENTATION_STATUS.md).
It does not assess food safety or replace a customer's own checks or contingency procedures.

## Quick start

Prerequisites: Docker Engine/Desktop with Linux containers and Compose v2.24+,
Python 3.13, and approximately 10 GB free disk space. GNU Make is optional.
The first build needs registry/internet access to pull the pinned images and dependencies.
For host browser tests also install Node 24 LTS and npm 11.

```sh
python scripts/dev.py setup
python scripts/dev.py up
python scripts/dev.py migrate
python scripts/dev.py test
```

Equivalent GNU Make commands: `make setup`, `make up`, `make migrate`, `make test`.
On Linux use `make PYTHON=python3` if `python` is not available. On Windows use
PowerShell with `python scripts/dev.py …`; no Bash or Make installation is required.
Setup generates unique local credentials in ignored `.env`, preserves existing values,
and appends missing template keys during upgrades.
Do not copy real credentials or customer data into this workspace. Never commit `.env`.

Open [the portal](http://127.0.0.1:5173), [health](http://127.0.0.1:8000/api/v1/health/),
[readiness](http://127.0.0.1:8000/api/v1/ready/), or [local mail sink](http://127.0.0.1:8025).
Only these loopback ports are published. PostgreSQL, RabbitMQ, Redis and SeaweedFS S3
are private to Docker. The worker handles local account reset mail only. Mailpit has no relay configured.
`up` runs migrations automatically before API/worker startup. The explicit migration command is idempotent.

## Developer commands

Every target below also works as `python scripts/dev.py <target>`.

| Target | Behavior |
|---|---|
| setup | Generate unique local configuration; preserve existing secrets |
| up | Build/start stack and wait for health; apply initial migrations |
| down | Stop project; preserve named data volumes |
| migrate | Apply committed migrations |
| seed-demo | Idempotently create two isolated fictional tenants with generated credentials |
| reset-demo | Requires `--confirm-local`; preserves identities and append-only evidence, deletes nothing |
| test | PostgreSQL-backed Pytest and frontend component tests |
| lint | Ruff lint/format, Django check/migration drift, ESLint/Prettier, TypeScript |
| build | Build all containers and frontend production bundle |
| contracts | Regenerate OpenAPI 3.1 and TypeScript types |
| auth-smoke | Verify synthetic reset delivery through RabbitMQ, worker and local SMTP |
| smoke | DB, broker/worker, Redis, SMTP; S3 authorization/isolation and synthetic object round-trip with cleanup |
| audit | Python and npm vulnerability scans; requires internet |
| secret-scan | Pinned offline Gitleaks against source-only staging, excluding local secrets |
| e2e | Host Playwright against the running stack |

Browser setup: `npm --prefix apps/web ci`, then from `apps/web` run
`npx playwright install chromium` (Linux CI: add `--with-deps`), then `npm run e2e`.
API code and frontend source are mounted; Django uses `--noreload`, so after API
edits run `docker compose restart api worker`. Vite polls mounted source for reliable Docker Desktop hot reload.
Dependency or Dockerfile changes require `up`/rebuild. See [dependency inventory](docs/DEPENDENCIES.md)
for exact versions, licence/support sources and lock refresh. SeaweedFS 4.48 replaces
archived MinIO under ADR-006; SEC-05 is resolved for the Sprint 01 local foundation.

## Manual demonstration

1. Start the stack; health returns exactly `{"status":"ok"}` and readiness returns `{"status":"ready"}`.
2. Open the portal: observe local-development warning, API reachable and no monitoring data.
3. Select Dansk. Navigation and explanations change; reload retains language preference.
4. Follow the Sprint 02 identity walkthrough below.
5. Press Tab from page load to use the skip link; inspect the portal at 390 px width.
6. Run `smoke`, `test`, `lint`, `build`. No real sensors, alerts or external providers are involved.

## Troubleshooting

- Docker engine denied/unavailable: start Docker Desktop in Linux-container mode and grant your account Docker access. Do not replace database tests with SQLite.
- Port occupied: stop the conflicting local service; the documented ports are intentionally fixed and loopback-only.
- Container unhealthy: `docker compose ps`, then inspect the affected service logs locally. Do not paste credentials or full resolved Compose config into reports.
- DB authentication after changing `.env`: setup preserves secrets; existing volumes retain their original credentials. Restore the original local `.env`; do not delete unknown volumes.
- Python dependencies are not needed on the host for normal use. All backend checks run in the Linux API container.
- Upgrading the initial MinIO stack: run `setup`, then `docker compose up --build -d --remove-orphans --wait`. This retires the MinIO container but retains its old named volume and legacy credentials. See the deployment guide; never attach a MinIO volume to SeaweedFS.
- Object-store startup refuses invalid credentials: generated S3 keys must be 64 lowercase hex characters. Setup preserves existing keys; restore valid local keys explicitly if they were edited.

See [implementation status](docs/IMPLEMENTATION_STATUS.md), [security register](docs/SECURITY_REGISTER.md),
[API](docs/API.md), and [deployment boundaries](docs/DEPLOYMENT.md). Git metadata was absent at handoff;
CI is supplied for a future GitHub repository, not remotely executed by this task.

Numbered sprints are authorized sequentially by the current user request. Live/customer/production gates remain separate.

## Sprint 02 identity walkthrough

Run `setup`, `up`, `migrate`, then `seed-demo`. The idempotent seed creates reserved
fictional A/B organisations, two planned sites per organisation, separate owners,
an operator with A1 access only, and a platform metadata administrator. It refuses
non-local settings and does not overwrite existing passwords, roles or audit data.

| Identity | Password source in ignored local `.env` | Scope |
|---|---|---|
| owner-a@example.invalid | DEMO_A_PASSWORD | Fictional A owner; MFA enrollment required |
| owner-b@example.invalid | DEMO_B_PASSWORD | Fictional B owner; MFA enrollment required |
| operator@example.invalid | DEMO_OPERATOR_PASSWORD | Fictional A1 only |
| platform@example.invalid | DEMO_PLATFORM_PASSWORD | Provision/list organisation metadata; no tenant-site bypass; MFA required |

Open `/login`, enter the local generated credential, add the displayed secret to
an authenticator and verify its code. Save the eight recovery codes shown once.
Use a fresh code for subsequent login or `/security` step-up; a used TOTP is rejected.
The owner can create planned sites, change metadata, invite users, assign/revoke
roles and deactivate memberships while retaining at least one owner. Sensitive
changes require password plus MFA confirmation within five minutes. Site admins
can grant only nonprivileged roles at their assigned sites. Platform staff cannot
browse customer sites through staff flags. All monitoring remains inactive.

Invitations and resets appear in [local Mailpit](http://127.0.0.1:8025). Links use
URL fragments, which the UI removes and keeps only in memory. New invitation
acceptance verifies the email; existing users must sign in first and confirm their
current password. Tokens expire (invitation 48h, reset 30m) and cannot be reused.
A reset revokes all sessions but preserves MFA. Recovery requires password proof,
a single-use recovery code, and fresh factor enrollment; it does not directly log
in or approve sensitive changes. Losing both factor and recovery codes has no
self-service administrative bypass. See ADR-007 before any manual recovery policy.

Run `auth-smoke` to exercise actual broker → worker → local SMTP reset delivery.
It creates one expiring reset link for the synthetic operator without consuming it
or changing the password. `e2e` requires `seed-demo`; it tests A1-only access and
logout through a real browser. Do not enable MFA/change the seeded operator for
repeatable browser checks; use another invited identity to explore MFA.


## Sprint 03 inventory

Run migrate and seed-demo after updating. Each fictional site receives one planned
building, room, gateway and sensor with **unknown calibration**; the seed creates
no approvals or fabricated drill results. Sign in as an owner, open Cold rooms &
sensors, select an allowed site, and use the inventory tabs. Configuration/evidence
writes require fresh step-up; calibration and acceptance need a separate site QA
role. An owner may grant that role explicitly in Users & permissions for synthetic
workflow testing. Read-only operators see inventory/warnings but no write controls.
See COMMISSIONING for the evidence workflow and real activation blockers.


Report builder: `/reports`, with current export roles, explicit timestamp offsets,
PDF/CSV, site/zone, polling and retry. `python scripts/dev.py report-smoke` exercises
actual generation and encrypted storage. Limits and retention: [REPORTS](docs/REPORTS.md).

Hardening checks: `security-check` verifies the non-owner SQL role, dropped Linux
capabilities, security headers, audit chains and rejection of corrupt/wrong-key
backups. `restore-drill` performs an actual isolated encrypted database/object
restore. `reference-load` creates a disjoint fictional 20-site/800-probe rig, sends
three real cadence rounds and gates measured receipt/rule/dashboard/TEST-delivery
results; it retires only its own rig and preserves evidence. `container-audit`
scans all eight image families without Docker socket or secret mounts. Do not
rebuild those images concurrently with the scan; retained per-image results can
be resumed with `scripts/container_audit.py --services <documented service names>`.
See [Sprint 10 evidence](docs/SPRINT_10_VERIFICATION.md),
[threat model](docs/THREAT_MODEL.md), [recovery](docs/RECOVERY.md) and
[container findings](docs/CONTAINER_SECURITY.md). All commands are local only.

Adapter preparation: `/integrations` and `python scripts/dev.py adapter-smoke`.
Only the read-only software simulator profile exists. See
[SDK contract](docs/ADAPTER_SDK.md), [pilot checklist](docs/PILOT_CHECKLIST.md) and
[Sprint 11 evidence](docs/SPRINT_11_VERIFICATION.md). Actual hardware/sites remain
blocked; a synthetic review never authorises go-live.

## Sprint 12 local commercial/support handover

`/billing` provides owner/platform usage, technical plan templates, recent-MFA
contact/term controls and immutable manual draft CSV. `/help` provides granted-site
status, onboarding, internal support and bounded acceptance references. No payment
is collected and commercial expiry never suspends existing monitoring.
`python scripts/dev.py commercial-smoke` exercises real local MFA and a zero-value
synthetic draft/export. adapter-smoke, security-check, restore-drill and reference-load
cover the local SDK, privileges, recovery and bounded performance drills.
See COMMERCIAL.md, OPERATIONS.md, CUSTOMER_TRAINING.md and RELEASE_REVIEW.md in docs.
Production remains BLOCKED; no actual hardware, customer data or P1/P2 is authorized.
