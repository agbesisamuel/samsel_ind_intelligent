# Requirements traceability

| Req ID | Description | Priority | Sprint | Implementation path | Test IDs | Status | Notes |
|---|---|---|---|---|---|---|---|
| EP-01 | Runnable monorepo foundation | P0 | 01 | apps/, compose.yaml, scripts/ | 32 backend + 5 component + 1 E2E; infra/S3/negative/persistence checks | TESTED | Sprint 01 complete; SEC-05 resolved via ADR-006 |
| NFR-07 | Security groundwork | P0 | 01/10 | config/, CI | Default-deny, environment guards, audits, secret scan | IN PROGRESS | Sprint 01 baseline tested; production assurance later |
| NFR-09 | Danish/English interface | P0 | 01–12 | i18n/, domain screens | Component/browser locale, DST and mobile checks | TESTED | Local English/Danish flows; no customer training sign-off |
| NFR-12 | Automated quality baseline | P0 | 01–12 | tests/, .github/, scripts/ | 170 backend, 14 component, 2 browser; strict lint/build/contracts and actual local drills | TESTED | Local CI equivalents; remote CI not run, no production acceptance |
| AUTH-01/02, TEN-01, AUD-01 | Identity, tenancy and audit | P0 | 02 | accounts/, tenants/, audit/, Identity/Administration UI | T-09/T-22, invite/reset/recovery, DB guards, actual SMTP/browser | TESTED | 63 backend/8 component/2 browser; verified SMTP; no production assurance claim |
| ASSET-01..05, TEN-02 | Assets and commissioning | P0 | 03 | sii/assets/, Inventory UI | T-07/T-20, 15 new backend cases, inventory browser checks | TESTED | Synthetic evidence only; real activation blocked; 78 backend/9 component/2 browser final |
| ING-01..04, ING-06 baseline, NFR-02 | Durable telemetry | P0 | 04 | sii/telemetry, MQTT/TLS Compose, simulator | T-04..06; 16 backend cases, 1,000-event transport/restart drill | TESTED | Synthetic only; durable receipts/tenant guards; CSV baseline |
| ING-05, ING-07 | Freshness and complete CSV | P0 | 05 | sii/monitoring, telemetry/views/services | T-15..17/T-21; DST/zero/skew/manual/backfill/policy tests | TESTED | Independent watcher; explicit QA timing; mapped preview revalidates on commit |
| DASH-01/02, UX-01 | Observation dashboard | P0 | 05 | Monitoring.tsx, scoped series/raw/latency APIs | 102 backend/10 component/2 browser final | TESTED | Synthetic only; hourly gaps/quality counts, raw inspector, localized site timestamps |
| DASH-03 | Incident centre | P0 | 08 | incidents/, Incidents.tsx | 12 incident cases; browser timeline/role checks | TESTED | Scoped workflow, immutable history, constrained encrypted attachments, activity export |
| RULE-01..05 | Approved deterministic rules | P0 | 06 | rules/, incidents/, Rules.tsx | T-01..03/T-08; 12 rule cases plus regression/browser | TESTED | Immutable QA versions, deterministic duration/gaps/recovery; synthetic only; rapid change requires qualified profile |
| ALERT-01/02/04..06 | Delivery and escalation | P0 | 07 | notifications/, Notifications.tsx, notification_smoke.py | T-10..12; 11 cases plus actual TEST capture | TESTED | Local only; consent, bounded retry, uncertain/dead visibility; human response is Sprint 08 |
| ALERT-03 | Human response | P0 | 08 | incidents/workflow.py | Replay/revision/QA/MFA/recurrence/closure tests | TESTED | QA independent; recovery never closes automatically |
| REPORT-01..02 | Evidence reports | P0 | 09 | reports/, Reports.tsx | Eight report cases, PDF/CSV worker drill | TESTED | Scoped immutable encrypted local reports; no production approval |
| NFR-01..08/10..11, AUTH-03 | Production assurance | P0 | 10/11 | support/, events/, scripts/, THREAT_MODEL.md | Runtime negative tests, actual load/restore/TEST drills | BLOCKED | Local controls tested; image remediation, external/cloud/site approval outstanding |
| BILL-01, EP-09 | Local commercial/support | P0 | 12 | billing/, support/desk.py, Billing/Help UI | Eight backend cases, commercial-smoke, real browser support flow | TESTED | Technical quotas/manual drafts only; production release blocked |





## Sprint 09 traceability

REPORT-01/02: reports models, snapshot/render/services/views and worker; Reports.tsx;
reports migrations/0001..0002; test_reports.py; report-smoke; ADR-014 and REPORTS.md.
T-tenant/export/DST/gap/retention/retry boundaries covered. REPORT-03 remains optional.

## Sprint 10 traceability

AUTH-03: support models/services/views and four security/negative tests. AUD-01/
NFR-08: restricted DB role, hash verifier, encrypted restore checkpoint comparison.
NFR-02/03/04/05: reference_load, fixed 16-shard transport, 2,400-event passing local
baseline and 80 TEST alerts. NFR-06: actual isolated restore; scheduled cloud RPO
not proven. NFR-07/11: inventories/threat model completed locally, production
remediation/external review BLOCKED. NFR-12: 155 unique backend, 13 component, two
browser checks plus actual transport/mail/storage/report/restart drills.

## Sprint 11 traceability

ASSET-03/ING-06 pilot preparation: sii/adapters SDK/model/views/SQL guards,
Integrations.tsx, seven adapter cases, browser blocker/scope checks and actual TLS
adapter-smoke. Simulator fallback verified; partner-approved hardware, two actual
pilots and physical/customer sign-offs BLOCKED. No live go-live path enabled.

## Sprint 12 traceability

BILL-01/EP-09: billing models/services/views, generated 0001 plus owned SQL 0002/0003;
support generated 0003 plus SQL 0004; tenant/asset expansion admissions; runtime
plan privilege revocation. Billing/Help UI uses generated contracts and current scope.
Eight new cases cover quotas/API/raw concurrent writes, expiry/current ingestion,
manual finance/CSV/idempotence/term history, tenant/operator/platform boundaries,
immutable support/history and independent incident state. Operational blockers and
bounded archive do not grant download or live activation rights. COMMERCIAL,
OPERATIONS, CUSTOMER_TRAINING and RELEASE_REVIEW document handover and external gates.
Exact final results and limitations: SPRINT_12_VERIFICATION.md. P1/P2 DEFERRED.
