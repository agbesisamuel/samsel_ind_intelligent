# Identity, tenant and foundation API

Sprint 08 incident response adds revisioned replay-safe commands, eligible assignees,
constrained encrypted attachments/downloads and authorized JSON activity export.
See INCIDENT_WORKFLOW.md. Provider acceptance, observed recovery and human closure
are separate fields/events; exact site grants and independent QA remain mandatory.

Sprint 07 adds exact-site notification consent/candidates/routes, TEST drills,
delivery attempts and worker/queue health. See NOTIFICATIONS.md. Every recipient
confirms personally; route mutation requires management plus recent MFA. No provider
acceptance changes incident acknowledgement or safety status.

Sprint 06 adds exact-site rule-families, immutable rule-versions, per-version
backtests/approve/activate, maintenance, incidents and incident-event reads. See
RULES.md for approval, scope, replay and synthetic-only invariants. Human incident
response is introduced separately in Sprint 08.

The generated contract is `packages/api-contracts/openapi.yaml` (OpenAPI 3.1).
Run `python scripts/dev.py contracts` after changing serializers/views. Never edit
that file or `schema.d.ts` manually. Frontend health uses openapi-fetch; identity
transport uses generated schema types and a same-origin CSRF wrapper.

Public GET `/api/v1/health/`, `/ready/`, `/schema/` remain data-free operational
contracts as documented in Sprint 01. They do not establish monitoring readiness.

All routes below are under `/api/v1/`. Unsafe methods require CSRF, including
anonymous login, reset and invitation acceptance. GET `auth/csrf/` returns the
masked token; send it in `X-CSRFToken` with same-origin cookies. Sessions are
HttpOnly, SameSite=Lax and secure by default; only loopback local/test settings
allow HTTP. No browser bearer token or wildcard CORS is used. Responses are no-store.

| Route | Method / behavior |
|---|---|
| auth/login/ | POST email/password; returns complete, mfa or enroll; pending challenges grant no business access |
| auth/logout/ | POST destroys current server session |
| auth/invitations/accept/ | POST token/password; single use, verifies email; existing accounts require their authenticated session and current password |
| auth/password-reset/request/ | POST email; identical 202 for known/unknown identities; queued local mail |
| auth/password-reset/confirm/ | POST token/new password; revokes sessions and all reset tokens; retains MFA |
| auth/mfa/enroll/ | POST after password proof; returns seed for manual enrollment; never overwrites enabled MFA |
| auth/mfa/verify/ | POST code; consumes a new TOTP counter or single-use recovery code; recovery forces reenrollment |
| auth/step-up/ | POST password and unused TOTP; sensitive actions allowed for five minutes |
| me/ | GET current identity, current memberships and exact roles |
| organisations/ | GET scoped metadata; platform superuser may list/provision metadata via POST name/owner_email |
| organisations/{org}/ | GET scope; PATCH owner metadata with step-up |
| organisations/{org}/sites/ | GET granted sites; POST planned site by owner with step-up |
| organisations/{org}/sites/{site}/ | GET scope; PATCH owner/site-admin metadata/archive with step-up; no activation |
| organisations/{org}/members/ | GET owner roster or site-admin scoped roster; nested roles filtered |
| organisations/{org}/members/{member}/ | PATCH active by owner with step-up; protect final owner |
| organisations/{org}/invitations/ | GET managed scopes; POST exact email/role/site with step-up |
| organisations/{org}/invitations/{invite}/revoke/ | POST managed scope with step-up |
| organisations/{org}/roles/ | POST membership_id/role/site_id with step-up and exact authority |
| organisations/{org}/roles/{role}/revoke/ | POST exact authority; protect final owner |
| organisations/{org}/audit/ | GET owner timeline or site-scoped admin/QA/auditor evidence |

Collections use 50-item pagination (`count`, `next`, `previous`, `results`). Scope
is applied before pagination. Foreign/nested IDs return indistinguishable scoped
404s. Read-only ownership fields, service-state changes, and unknown input keys
are rejected. Role `owner` requires null site; all other roles require an exact
same-organisation site. Site admins cannot grant owner, site_admin or QA.

The error envelope is `{code,message,details,request_id}` with bounded messages;
model/constraint errors do not disclose foreign identifiers. Auth commands use
atomic PostgreSQL counters keyed by hashed IP/account and a fixed time window:
login 10/minute, MFA/step-up/enrollment 5/minute, reset request 5/30min; other
proof commands 10/minute. Counter cleanup never deletes audit. Forwarded headers
are not trusted as client identity. Deployment proxy/rate controls remain Sprint 10.

Every other view remains default-deny, including staff. No Django admin, device
credentials, ingest, monitoring, report or support-access API exists in Sprint 02.

## Sprint 03 inventory routes

Under `/api/v1/organisations/{org}/sites/{site}/`, resources `buildings`, `zones`,
`gateways`, `sensors`, `calibrations`, `sensor-commissionings`, `commissioning`,
`commissioning-tests` and `acceptances` expose scoped paginated GET collections and
GET `{id}/` detail. POST creates inventory/evidence except acceptances; PATCH amends
inventory metadata only. No DELETE. Ownership, external ID, parent assignments,
actor/provenance and lifecycle fields cannot be mass-assigned. Evidence cannot be
patched/deleted. Every submitted relation must match the URL organisation AND site.

POST `gateways/{id}/transition/` or `sensors/{id}/transition/` takes `target` for an
audited lifecycle transition; retirement is terminal and active remains gated.
POST `commissioning/{id}/accept/` requires explicit site QA and fresh step-up and
stores an immutable synthetic snapshot/hash. Acceptance `current` checks the live
configuration and qualification evidence against that snapshot. GET `activation/`
returns blockers; POST always denies local real monitoring with 409 and audit.
Sensor `qualification` includes current calibration status/due date and warnings,
never a fabricated reading or food-safety judgment. See generated schema for exact
fields and enum choices; no credential or ingestion API exists in Sprint 03.

## Sprint 04 API

Device HTTPS/MQTT routes and authentication are separate from human sessions. Exact
contracts, receipts, rotation/revoke, CSV baseline and scoped metrics are described
in TELEMETRY_PROTOCOL.md. Generated device schema is device-openapi.yaml; human
administration and reading schemas remain in openapi.yaml. Regenerate both with
`python scripts/dev.py contracts`. No production/live device operation is enabled.

## Sprint 05 endpoints and presentation

Nested site routes add `freshness-policy/`, `monitoring/`, `series/` and `latency/`.
Raw `readings/` accepts the same sensor/start/end window as hourly series; filtered
windows are capped at 31 days and raw results remain paginated. CSV adds explicit
column mapping and stable import IDs; preview/commit share domain checks. See
MONITORING.md and regenerated OpenAPI. Accepted/rejected broker messages now use
the full versioned tenant/site/correlation envelope and persisted-subject validation.

Reports: authenticated exact-site `/reports/` admission/list, `/{job}/retry/`,
`/{job}/access/` and `/{job}/downloads/{grant}/`. See REPORTS.md and generated schema
for strict inputs, roles, bounded windows, immutable cutoff and expiring access.

Sprint 10 support routes: exact-site `support-sessions/` GET/POST,
`support-sessions/{id}/revoke/` POST and `support-access/` GET are owner-only.
Approval/revoke require recent MFA. Independent staff use
`/api/v1/support-sessions/{id}/diagnostics/` with recent MFA and a current approved
capability; returned data is limited to aggregate health counts. The grant never
changes ordinary tenant access. See THREAT_MODEL.md and regenerated OpenAPI.

Sprint 11: exact-site `adapter-readiness/` GET returns software-only profile,
blocked live state and current scoped operational counts. `pilot-reviews/` GET/POST
lists/appends immutable synthetic daily/weekly reviews. POST requires current
operational scope and recent MFA; owner/site/actor/provenance overrides are denied.
No update/delete or hardware-control endpoint exists. See ADAPTER_SDK.md.

## Sprint 12 commercial and support contracts

Authenticated `/api/v1/plans/`; organisation `subscription/` GET/POST/PATCH,
`subscription/history/` GET, `invoices/` GET/POST and `invoices/{id}/export/` GET.
Owner/platform commercial metadata only; term/draft changes require platform and
recent MFA. Contacts require owner/MFA. Unknown/readonly inputs are rejected.
Exact-site `support-tickets/` GET/POST, `support-tickets/{id}/events/` GET/POST,
`operational-status/` GET and export-role `artifact-archive/` GET preserve current
scope, original evidence and revisioned replies. Status cannot enable production.
See COMMERCIAL.md/OPERATIONS.md. Regenerate strict human/device YAML and TypeScript
with contracts; never manually edit generated schemas or model migrations.
