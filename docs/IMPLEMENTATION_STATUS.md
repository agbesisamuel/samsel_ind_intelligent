# Implementation Status

- Current milestone: **Sprint 10 local implementation VERIFIED**; Sprints 01–09 complete locally. **Sprint 11 simulator/pilot-ready branch VERIFIED**. Sprint 12 IN PROGRESS.
- Earliest incomplete local software sprint: **12**. Sprint 10 production acceptance remains **BLOCKED** by container remediation, external security/legal review and production operational gates; it is not represented as production-ready.
- Authorization: the user's request permits the remaining numbered sprints sequentially. P1/P2, actual hardware/customer data, live alerts, paid services and production deployment require separate authorization.
- Master fully read; unchanged SHA-256 `BE70C9C7B871001AE77D4941A5E06C4F5DD6261A2E8F501DEF0FC84C33B9AB6C`. No Git metadata/remote exists; no remote CI claim.
- Implemented: identity/MFA/recovery; exact active tenant/site RBAC; inventory/qualification; durable TLS HTTPS/MQTT; independent freshness; immutable QA-approved rules; incident response/evidence; durable TEST notifications; asynchronous encrypted PDF/CSV reports; narrow owner-approved expiring support; runtime SQL role, audit verification, versioned domain transport and isolated recovery tooling.
- Latest verification: **155 unique backend tests** across full/targeted runs; **13 component + 2 Chromium tests** passed. Ruff (133 files), Django/migration checks, frontend lint/types, strict contracts and all image/frontend builds passed. Actual infrastructure/S3, TEST mail/reports and worker-restart transport drills passed. Exact evidence and corrected failures: `docs/SPRINT_10_VERIFICATION.md`.
- Reference load: 20 sites × 40 probes × 1/min for three cadence rounds, **2,400/2,400 accepted and processed**, 0 pending/errors; processing P95 **2.057935s**, dashboard P95 **0.203849s**, **80/80 TEST notifications**. This is not a 24-hour soak or field/cloud availability measurement.
- Recovery: fresh isolated DB/object containers, 3,940 readings, six decrypted artifacts and four audit chains; RTO **28.4293503s**, restored-audit age **438.312628s**. Scheduled production RPO/PITR remains unproven.
- Security: Python/npm lock audits 0 known application findings; full eight-image scans retain unresolved OS/vendor findings and explicit reachability limitations. **No clean production scan or security sign-off is claimed.** See CONTAINER_SECURITY.md and THREAT_MODEL.md.
- Runtime: loopback-only application/device/mail ports; private infrastructure and S3/control separation; restricted non-root application execution; local synthetic identities/rigs only. Domain receipts drained (0 pending/dead). No food-safety, actual compatibility or SLA claims.
- Storage: MinIO support exception resolved via maintained pinned SeaweedFS/nginx (ADR-006). Bounded local capacity increased to 32 sparse 128-MiB volumes after a real smoke capacity failure; repeated checks passed. Legacy MinIO/TLS volumes remain untouched and unmounted.
- Upgrade: setup → up → migrate → seed-demo, preserving generated secrets. Down preserves volumes. Never reverse security/evidence migrations or erase raw/audit records as cleanup. Preserve independent MFA/device/evidence/backup keys under reviewed custody.
- Remaining software: Sprint 12 plans/quotas/manual invoice export/help/onboarding/usage and operational release review. Sprint 11 SDK/immutable reviews/bilingual preparation are verified; actual hardware remains blocked.
- External gates: **BLOCKED: no authorised hardware/site** and **CUSTOMER/SUPPLIER APPROVAL REQUIRED**. No partner profile, physical calibration, actual pilot sign-off, cloud pager, customer agreement, legal approval or production deployment is fabricated.
- Documentation review: purpose/security documentation, behavior tests, generated-artifact workflow, threat/privilege/privacy/retention/recovery/incident notes and exact evidence reviewed. Literal Make/remote CI not run; documented Python equivalents executed.

## Milestone history

Initial inspection found only the master and three srs documents, no code/manifests/
Git metadata. Sprint 01 created the full local stack and starter checks. Its results
are retained in SPRINT_01_VERIFICATION and SPRINT_01_STORAGE_VERIFICATION. Sprint 02
added identity/tenancy on that foundation; it does not claim later domains complete.


## Sprint 03 completion

ASSET-01..05/TEN-02 implemented locally: scoped building/zone/gateway/sensor tree,
planned/commissioning/degraded/retired transitions, calibration expiry/unknown
warnings, append-only placement/test/site-pack and explicit QA acceptance snapshots.
Sensor/current configuration changes invalidate acceptance currency without changing
history. Active/live monitoring remains denied. One-time credential provisioning
design is documented; transport enforcement belongs to Sprint 04.

Added generated assets/0001 and /0003 plus documented SQL /0002 guards. Applied,
no drift. Bilingual inventory UI, exact scope/role controls and planned-only demo
inventory. Final checks: **78 backend, 9 component, 2 browser tests passed**;
lint/types/migrations/contracts, image/frontend builds, healthy stack, infrastructure/
S3 checks and secret scan (0 leaks) passed. No new dependencies. Exact results and
limits: SPRINT_03_VERIFICATION.md. Remote CI/live-site/production checks not run.
Documentation review complete; master and historical verification reports preserved.

## Sprint 04 completion

ING-01..04/ING-06 baseline/NFR-02 implemented and tested: separate TLS device API,
RabbitMQ MQTT vhost/topic ACL/HMAC, one shared validator, append-only scoped readings,
quarantine metadata and durable idempotent outbox processing. Device issuance/rotation/
revoke and exact scope are enforced; retired/unqualified input rejected. CSV baseline
is manual/imported. Seeded simulator persists its spool and exercises both transports.
Applied assets/0004 and telemetry/0001..0003; no drift. Added Paho 2.1.0, hash locked.
1,000 accepted/12 rejected/100 duplicates/0 pending after worker restart; additional
100-event run verified actual foreign-topic denial. All listed regression/build/audit
checks passed. Eleven services healthy. Protocol/ADR-009 and verification documents
record limitations and rollback/retention boundaries. No live activation enabled.

## Sprint 05 completion

ING-05/07, DASH-01/02 and UX-01 implemented/tested locally. Independent watcher,
QA-approved cadence/grace snapshot, immutable freshness transitions, no-data/stale/
offline/unqualified/quality/policy-missing/delayed states. Scoped cross-site/zone
dashboard, UTC-hour aggregates with DST/gap preservation, raw paginated inspector,
two-clock provenance and exact processing P95/sample size. CSV mapping has bounded
domain-complete preview and revalidated manual commit. Added monitoring/0001..0002;
telemetry/0004..0005 complete versioned accepted/rejected event envelopes and scope.
All final checks passed as recorded above. No dependency changes or actual site
approvals. Documentation and generated artifacts reviewed; next numbered sprint 06.

## Sprint 06 completion

RULE-01..05 and incident evidence implemented/tested: immutable version/backtest/QA
approval/effective boundaries, duration/completeness/hysteresis/gap engine, independent
no-data/offline/invalid classifications and visible expiring maintenance. Retry is
idempotent; recovery preserves open human work; late/backfill cannot rewrite live
history. Bilingual rule authoring/preview UI and scoped evidence reads. Generated
rules/incidents migrations and explicit SQL guards applied. Exact checks/initial
browser readiness failure and final passing rerun: SPRINT_06_VERIFICATION.md.
Rapid-change remains unavailable without a qualified adapter; real go-live blocked.

## Sprint 07 completion

Verified personal recipient opt-in, immutable scoped routes with timezone/shifts/
severity, non-acknowledgement escalation and contingency. Persisted event-plan ledger,
delivery intents, immutable attempts, bounded retry, uncertain/dead states and visible
support issues. Maintenance expires and rechecks delivery. Independent dispatcher,
bilingual health/consent/route UI and actual TEST capture drill integrated into CI.
All final checks passed as recorded in SPRINT_07_VERIFICATION.md. No live provider or
paid sends; provider acceptance remains distinct from human response. Next sprint 08.

## Sprint 08 completion

ALERT-03/DASH-03 and domain AUD-01 baseline: explicit human response states,
independent QA/MFA review/close, observed recovery requirement, replay/revision
protection and immutable amendments. Renewed breaches invalidate review. Exact-site
assignment is DB/service guarded; provider acceptance stays separate. Bilingual
timeline/action/filter UI, authorized JSON activity export and UTF-8-only encrypted
evidence attachments with audited scoped downloads. SDK versions/SQL migrations,
actual S3 proof and exact checks recorded in SPRINT_08_VERIFICATION.md. Broader upload
formats/production assurance remain gated. Next sprint 09.

## Sprint 09 completion

REPORT-01/02: bounded asynchronous PDF/CSV, fixed receipt cutoff and immutable source
snapshot, qualified coverage/gaps, calibration/rule/incident chronology, encrypted
private artifacts, checksum/audit and identity-bound expiring single-use downloads.
Bilingual builder/list/retry/export restrictions; report worker and CI smoke command.
145 unique backend tests, 13 component and 2 browser tests passed across full/final
runs; exact results and initial corrected failures in SPRINT_09_VERIFICATION.md.
Final PDF visually inspected. Documentation/code review complete. Next sprint 10.


## Sprint 10 local implementation checkpoint

AUTH-03 and AUD/NFR hardening delivered locally. Support/events migrations and
DB guards, restricted runtime role, non-root application execution, immutable
source-bound domain contracts, measured 16-shard telemetry, encrypted recovery,
SBOM/licence/image inventory and threat/playbooks are implemented and tested.
Exact commands/results and initial failures: SPRINT_10_VERIFICATION.md. Production
acceptance is blocked by the recorded image/security/legal/cloud/site gates.
Only the explicitly permitted simulator/pilot-ready Sprint 11 branch proceeds.

## Sprint 11 simulator checkpoint

Read-only SDK, durable gateway-bound buffered replay/source clocks, scoped readiness
and immutable synthetic daily/weekly reviews, bilingual UI and pilot checklist
implemented. 162 backend, 14 component and two browser tests passed; actual TLS
SDK drill 3 accepted/3 duplicate/0 pending. Lint/contracts/builds/audits/source scan
passed; exact results in SPRINT_11_VERIFICATION.md. No authorised hardware/site;
no actual profile, physical QA or customer sign-off inferred. Next software sprint 12.
