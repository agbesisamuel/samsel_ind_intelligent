# SAMSEL Industrial Intelligence
## Software Product Requirements Specification (PRD + SRS + Implementation Backlog)

**Owner:** SAMSEL Group ApS | **CVR:** 46840070  
**Version:** 1.0 | **Prepared:** 20 October 2026  
**Project type:** Fully proprietary cloud-based, multi-tenant B2B SaaS  
**Initial industries:** Food processing, refrigerated and frozen warehouse operations  
**Document status:** Proposed product requirements; subject to pilot interviews, security review, contractual limits and technical feasibility

> **Key safety boundary:** The system is a decision-support and recording service, not a direct refrigeration controller or a substitute for the food operator's HACCP responsibilities. Temperature limits, monitoring frequency, corrective actions, accountability and retention must be determined by the customer with competent food-safety personnel. Sensor failure, loss of connectivity, notification failure and incident nonresponse must be treated as first-class states.

# 1. Product vision, goals and exclusions

**Vision:** Provide a trusted, easy-to-use control centre for cold-chain monitoring and operational intelligence across one or more food-industry sites.

**MVP business goals:** (G1) onboard two paid supervised pilots; (G2) ingest and display qualified temperature readings with explicit freshness; (G3) reliably detect threshold and missing-data events; (G4) provide accountable alarm escalation and corrective-action evidence; (G5) give managers usable PDF/CSV records; (G6) demonstrate secure multi-tenancy and measurable support costs.

**Post-MVP goals:** cross-site comparisons, authorised electricity-meter feeds, equipment utilisation and energy anomalies, multi-country localisations, optional prognostics on verified data.

**Out of scope for MVP:** writing to industrial PLCs; remotely changing temperature setpoints or starting compressors; automated food safety certification; assigning universal critical limits; autonomous discard/release decisions; integrated accounting; mobile native apps; public APIs beyond necessary connectors; AI-based predictions advertised as certain; medical/pharma GxP workflows.

# 2. Product principles and control boundaries

1. **Read only:** The SAMSEL gateway must not have remote-control permissions on customer equipment. Strictly outbound data path from customer site to cloud by default.
2. **Traceability:** Keep original sensor reading, receive timestamp, data origin, units, calibration reference and subsequent corrections separately; never silently replace raw evidence.
3. **Observable failure:** Disconnected probes, failed delivery routes and unknown readings are displayed as unavailable/uncertain rather than green.
4. **Customer-defined rules:** Temperature bounds vary by stored food, process and customer policy. No hard-coded 'safe food' thresholds or one-size-fits-all HACCP settings.
5. **Tenant isolation:** Every record, request, batch job, event and notification has explicit tenant scope; every cross-tenant access is rejected and tested.
6. **Human oversight:** The operator decides whether food is safe and what to do when an alarm occurs. Platform advice is non-authoritative.
7. **Owned IP:** Application components and analytics authored under SAMSEL's contracts are proprietary to SAMSEL. Standard OSS infrastructure and third-party sensor hardware are permitted and tracked in an SBOM.

# 3. Actors, roles and permissions

| Role | Principal access | Forbidden access |
|---|---|---|
| SAMSEL Super Admin | Tenant provisioning, subscription state, support session approval and system-wide health | Reading all customer data by default or silently impersonating users |
| SAMSEL Support Analyst | Time-limited, logged tenant-scoped support with customer approval | Editing raw sensor readings or bypassing alarm audit |
| Customer Organisation Owner | Users, sites, integrations, plan settings, audit exports | Access to other organisations |
| Site Admin | Site assets, rule configuration, user/site assignments | Global billing or other sites unless delegated |
| QA / HACCP Manager | Approve threshold versions, incidents, corrective actions, exports | Remove immutable source records |
| Operations Manager | Monitor assets, assign incidents, reports | Change audited critical limits without approval |
| On-call Operator | Acknowledge assigned alerts, record actions | Edit thresholds or audit history |
| Auditor (read-only) | Explicit scoped reports and audit trail | Configure alarms, view billing or edit records |
| Device / Gateway | Submit signed telemetry for assigned gateway/sensors only | Access customer users, reports or other devices |

A user may hold multiple site-scoped roles. Enforce role- and object-level permission checks in backend services; UI hiding alone is insufficient. SAMSEL administrative access uses time-bound elevation and records purpose.

# 4. End-to-end user journeys

**J1 – Onboard a site:** Sales handoff -> customer organisation owner invitation -> site and zone creation -> contract scope -> qualified gateway registration -> commissioning tests -> QA sets and approves rules -> notification contacts tested -> customer signs acceptance -> activation.

**J2 – Threshold excursion:** Sensor sends temperature -> validation and quality flags -> durable storage -> rule evaluation with sustained duration and hysteresis -> incident opens -> priority defined -> notifications attempted -> employee acknowledges -> corrective action recorded -> QA verifies and closes -> report preserves all events.

**J3 – Loss of data:** Expected sample not received within site-approved timeout -> explicit data-gap event -> alert escalation (different from temperature excursion) -> customer investigates power/connectivity/probe -> data resumes -> gap remains in reports; late readings are clearly marked.

**J4 – Audit evidence:** QA filters by site, room, batch/period and incident status -> platform creates time-stamped PDF/CSV archive with data-coverage and calibration notes -> authorised user downloads -> export activity appears in audit log.

**J5 – Energy review (phase 2):** Authorised meter/energy readings imported -> tariffs and period aligned -> consumption baseline and deviations computed -> operator reviews actionable findings; never labels projected savings as verified without a measured intervention protocol.

# 5. Functional requirements: Must-have MVP (P0)

Each requirement ID shall have associated automated tests and traceability to acceptance criteria. "P0" means release-blocking. Numeric thresholds below are engineering targets, not commercial SLAs until empirically validated.

## 5.1 Authentication, tenancy and commercial administration

| ID | Requirement | Acceptance / verification |
|---|---|---|
| AUTH-01 | Invite-only organisation registration, verified email, password reset, MFA for privileged roles | Expired/replayed invite rejected; MFA required for site admin/QA/SAMSEL admin |
| AUTH-02 | Role-and-site scoped permission enforcement | API returns 403 to unauthorised user; automated cross-tenant matrix passes |
| AUTH-03 | Support break-glass workflow with approval, expiry, reason and audit | Customer sees who accessed their site and when; privilege expires |
| TEN-01 | Multi-tenant organisations, sites, zones, assets, gateway ownership | No tenant data visible through URL, query, export or background job |
| TEN-02 | Soft delete for operational configuration with immutable history | Historic incidents retain reference to rule/device version |
| BILL-01 | Subscription state, seat/device/site quotas, invoices export and trial end | Quota enforced server-side with customer-visible warnings |
| AUD-01 | Append-only administrative and critical workflow audit log | Actor, before/after, timestamp and reason tracked; log integrity checked |

## 5.2 Asset and sensor inventory

| ID | Requirement | Acceptance / verification |
|---|---|---|
| ASSET-01 | Represent sites, buildings, cold rooms, freezer rooms, zones, probes and gateways | Zones have unique IDs, timezone, expected data cadence and responsible staff |
| ASSET-02 | Record probe type, unit, range, last calibration, accuracy/source and placement notes | Expired/unknown calibration visibly flagged in all evidence exports |
| ASSET-03 | Commission sensors with recorded test date and responsible technician | Activation blocked until critical device tests and alarm routes pass |
| ASSET-04 | Maintain lifecycle states: planned, commissioning, active, degraded, retired | Retired devices cannot write new data without a new provisioning event |
| ASSET-05 | Capture room type and product/SOP tags without prescribing critical limits | Rule limits require site-specific QA approval |

## 5.3 Industrial ingestion and data fidelity

| ID | Requirement | Acceptance / verification |
|---|---|---|
| ING-01 | Receive gateway telemetry through authenticated HTTPS and secure MQTT | Reject missing/expired credentials; only registered devices accepted |
| ING-02 | Persist measurement, source timestamp, receive timestamp, sequence/id, units, quality flags | Raw payload/event retrievable for audit and troubleshooting |
| ING-03 | Validate device, schema, numeric ranges, timestamp skew, duplicates and replay | Invalid readings quarantined, not silently converted into safe observations |
| ING-04 | Support idempotent retries and late/out-of-order messages | Same event ID counted once; original and arrived-late markers preserved |
| ING-05 | Identify stale sensor and gateway heartbeat gaps independently | Simulated lost connection creates correct no-data incident within configured grace |
| ING-06 | Buffer locally on eligible gateways and forward when internet returns | Backfill is marked, without retroactively cancelling past alert history |
| ING-07 | CSV import with explicit source type, unit mapping, provenance and timestamp timezone | Invalid rows reported; imported data not misrepresented as live sensing |

**Technical note:** Do not assume ElOverblik meter imports are real-time temperature sensors. Meter data belongs in a separate energy pipeline and requires customer authorisation and third-party registration where applicable.

## 5.4 Rule evaluation and alert lifecycle

| ID | Requirement | Acceptance / verification |
|---|---|---|
| RULE-01 | Versioned lower/upper temperature limits per zone, with effective dates and QA approval | Every incident references exact rule version and authorising user |
| RULE-02 | Sustained-duration breaches, debounce, hysteresis and recovery logic | One sustained breach opens one incident; normal oscillation does not spam |
| RULE-03 | Rule categories: too warm, too cold, rapid change, device offline, gateway offline, invalid reading | Distinguishable severity and guidance for each condition |
| RULE-04 | Maintenance/suppression windows that retain raw data and explicit suppression audit | Suppression cannot silently erase events; prominent visual warning shown |
| RULE-05 | Engine produces idempotent incident events and alert jobs via durable queue | No incident lost due to a transient worker restart in tested scenarios |
| ALERT-01 | Notification routes by site, shift, severity and escalation time | Simulated unacknowledged critical alert triggers next available contact |
| ALERT-02 | Email notifications P0; SMS optional only after provider delivery and cost tests | Attempts, provider acceptance/failure and retries recorded separately |
| ALERT-03 | Acknowledge, assign, add comments, corrective actions, resolve, QA verify | Closure requires outcome, actor and appropriate reason/evidence |
| ALERT-04 | Alert dry-run/test mode with full workflow and audit record | Customer commissioning includes documented contact-route test |
| ALERT-05 | Prevent duplicate floods and display data-quality state | Replayed or delayed sensor events do not incorrectly close critical incidents |
| ALERT-06 | Failure of notification provider shown in support status and retry/backoff queue | System records failed attempts and warns customer when route is unavailable |

**Safety rule:** Provider acceptance or an email/API 200 is not proof that a person received or acted upon an alarm. Do not describe the system as guaranteeing notification receipt or response.

## 5.5 Dashboards, reporting and investigation

| ID | Requirement | Acceptance / verification |
|---|---|---|
| DASH-01 | Cross-site status, latest valid reading, reading age, device health and open incidents | Degraded/offline is visually distinct from 'normal'; no false green |
| DASH-02 | Time-series charts, timezone labels, filters, raw-vs-aggregated display | Drilldown matches recorded raw data within explicit aggregation tolerance |
| DASH-03 | Incident timeline with threshold, acknowledgements, attempts and corrective actions | User can reconstruct order of events and identify unmonitored intervals |
| REPORT-01 | Generate period-based PDF/CSV temperature and alarm report | Includes reporting interval, timezone, missing data and generation metadata |
| REPORT-02 | Record evidence versions, audit trail and exports | Export access is logged; regeneration does not alter source records |
| REPORT-03 | Scheduled report delivery to verified recipients, optional P1 | Failures surface; access links authenticated and time-limited |
| UX-01 | Responsive Danish/English user interface; accessible critical alert status | Keyboard operation, explicit text states and WCAG 2.2 AA design target |

# 6. Prioritised features beyond MVP

| ID | Phase | Requirement | Dependencies |
|---|---|---|---|
| EN-01 | P1 | Energinet ElOverblik third-party-authorised metering imports | Registration, customer mandate, live API feasibility |
| EN-02 | P1 | Electricity tariffs, consumption breakdown and price trends | Consistent interval data, customer tariff inputs |
| EN-03 | P1 | Refrigeration consumption baselines and abnormal-hours flags | Sufficient historical data and operational schedules |
| MAINT-01 | P1 | Refrigeration equipment runtime, door-open and defrost-cycle event tracking | Validated sensor/PLC adapters, read-only access |
| INT-01 | P1 | Documented customer REST API and outbound webhooks | Stable RBAC scopes, rate limits and versioning |
| COM-01 | P1 | Danish invoices/e-invoicing integration | Accountant review and billing partner selection |
| ENT-01 | P2 | SSO/SAML or OIDC enterprise login | Enterprise demand and security design |
| LANG-01 | P2 | Swedish, German and Dutch locale packs | First-country partner and legal feasibility |
| PRED-01 | P2 | Machine-health risk modelling with confidence and human review | Validated failure-labelled datasets and monitoring bias review |
| MOBILE-01 | P2 | Native apps only if on-call adoption requires them | Product-market and secure mobile requirements |

**AI use policy:** Do not enable opaque ML to determine whether food is safe. Use interpretable trend analysis first. Any generative AI should produce clearly labelled optional summaries from audited records and must never overwrite raw logs or critical alerts.

# 7. Data model and schema design

**Primary SQL entities (all tenant-scoped where relevant):** Organisation; Contract; Subscription; User; Membership; RoleAssignment; Site; Building; Zone; Asset; Sensor; Gateway; DeviceCredential; CalibrationRecord; SensorCommissioning; TelemetryRaw; TelemetryQualityFlag; SensorHeartbeat; Ruleset; RuleVersion; RuleApproval; Incident; IncidentEvent; AlertRoute; EscalationPolicy; NotificationAttempt; Acknowledgement; CorrectiveAction; QAReview; ReportJob; ExportArtifact; IntegrationConnection; EnergyMeter; EnergyReading; AuditEvent; SupportSession; DataRetentionPolicy; DataDeletionJob.

**Suggested key fields:**

- `organisation(id, name, country_code, timezone_default, contract_status, created_at)`
- `site(id, organisation_id, name, timezone, service_state, emergency_contact_policy_id)`
- `zone(id, organisation_id, site_id, name, type, operating_sop_ref, criticality)`
- `sensor(id, organisation_id, gateway_id, zone_id, external_id, unit, expected_interval_sec, calibration_due_at, state)`
- `telemetry_raw(id, organisation_id, sensor_id, event_uuid, recorded_at_utc, received_at_utc, value_decimal, unit, payload_hash, quality_flags, source)`
- `rule_version(id, organisation_id, zone_id, threshold_min, threshold_max, sustained_seconds, hysteresis, effective_at, approved_by, approval_at, state)`
- `incident(id, organisation_id, zone_id, sensor_id, rule_version_id, type, severity, opened_at, status, owner_user_id, closed_at)`
- `notification_attempt(id, organisation_id, incident_id, channel, recipient_id, provider_id, attempt_at, provider_status, delivery_evidence)`
- `corrective_action(id, organisation_id, incident_id, author_id, action_type, description, recorded_at, evidence_uri, qa_approved_at)`
- `audit_event(id, organisation_id, actor_id, action, subject, occurred_at, prev_hash, event_hash, metadata)`

**Constraints:** Strong unique `(organisation_id, sensor_id, event_uuid)` on ingestion; foreign keys validate same-tenant ownership; UTC storage with explicit site timezone for presentation; quantity units standardised in canonical storage, raw units retained; immutable raw telemetry, corrections as appended annotations, never UPDATE original evidence. Large telemetry tables partitioned or use supported PostgreSQL time-series extension after licensing/performance evaluation. Use schema migrations and retention-eligible cold storage rather than unbounded row retention.

**Data retention (draft, contract-driven):** Configurable retention per tenant and record class. Example defaults for quotation only: high-frequency raw telemetry 12 months, derived minute aggregates 36 months, incident/evidence 36 months; verify customer HACCP/legal/insurer requirements before making defaults binding. Allow legal hold, export before deletion, documented purge and backups lifecycle. Do not assert a universal statutory food-monitoring retention period.

# 8. Proposed architecture

## 8.1 Fully proprietary application with standard infrastructure

**Frontend:** React, TypeScript, Vite (depending on SSR needs), responsive design system, accessible charts and Danish/English localisation. No industrial control code in browser.

**API/business services:** Django REST Framework with versioned REST endpoints, strict RBAC, PostgreSQL, server-side input validation, OpenAPI 3.1 documentation. The API layer is proprietary to SAMSEL.

**Device ingress:** Dedicated proprietary ingestion service in Python or Go, secure MQTT and HTTPS endpoints, schema validation, device identity, deduplication and quality tagging. Standard OSS MQTT broker is infrastructure, not a white-label monitoring platform.

**Processing:** Durable message queue (RabbitMQ, Redis Streams or managed equivalents), Celery or dedicated workers, idempotent event handlers, separate rule engine, incident service and notification dispatcher. Choose one supported queue and implement dead-letter processing and replay.

**Storage:** PostgreSQL for business entities, partitioned/time-series storage for readings, EU-region encrypted object storage for reports/raw payload backups, Redis for caches/rate limits, independently stored immutable audit records.

**Operations:** Infrastructure-as-code, containerised deployments, EU-region cloud provider, managed secrets, monitoring and traces, log centralisation, backup/restore, automated deploy and security scanning. Use staging with synthetic data, separate from production.

**Integration boundary:** Existing certified/qualified third-party temperature sensors through approved gateways or documented cloud APIs. Gateway firmware/software must be separately threat-modelled and potentially assessed under CRA. Sensor procurement and electrical commissioning handled by qualified partners.

## 8.2 Architecture diagram (logical)

```text
Customer site: sensors -> approved industrial gateway
                           |  (outbound HTTPS / MQTT over TLS)
                           v
                Cloud ingress / MQTT broker
                           |
                  auth + payload validation
                           v
                      durable queue
                           |
              +------------+-------------+
              |                          |
       proprietary data writer    proprietary rules engine
              |                          |
      PostgreSQL/time-series             incident/event store
              |                          |
              +----------+---------------+
                         |
                 Django REST APIs
                         |
                 React web portal
                         |
           customer users / QA / operations

Notification worker -> email/SMS providers (separate attempts & audit)
Report worker -> encrypted object storage (auth-gated PDF/CSV)
Customer identity / billing / support admin -> scoped business APIs
```

**Network principle:** No inbound connection from internet into plant OT controls. Gateway initiation outbound only; coordinate with plant IT. Device credentials scoped to individual devices; rotate/revoke independently. Never place an exposed Modbus endpoint on the public internet.

## 8.3 Deployment strategy

Start as a modular monolith for customer/business functions plus a separately scaled telemetry ingestion/rules pipeline. Avoid premature microservice complexity, but preserve clear domain boundaries in packages and data contracts. Separate production, staging and development. Choose cloud based on Danish/EU data residency, audit features, managed PostgreSQL, backups, cost controls and team capability, not merely branding.

# 9. APIs, event schemas and integration contracts

All HTTP APIs use `/api/v1/`, HTTPS, pagination, input validation, rate limiting, trace IDs and OpenAPI documentation. User API authenticated with server sessions or scoped OAuth/OIDC tokens; gateways have separate device identity. Never reuse human authentication tokens as gateway credentials.

| Endpoint (illustrative) | Method | Role | Operation |
|---|---|---|---|
| `/organisations/{id}/sites/` | GET/POST | Owner/Site admin | List or create site within access scope |
| `/sites/{site_id}/zones/` | GET/POST | Site admin | Zones and SOP identifiers |
| `/zones/{zone_id}/sensors/` | GET/POST | Site admin | Sensors and commissioning |
| `/devices/{device_id}/telemetry/` | POST | Device only | Authenticated batch ingestion (alternate MQTT topic) |
| `/zones/{zone_id}/readings/` | GET | Viewer+ | Time-series, with quality status |
| `/zones/{zone_id}/rules/` | GET/POST | QA/site admin | Draft/configure threshold versions |
| `/rules/{version_id}/approve/` | POST | QA manager | Activate approved critical rules |
| `/incidents/` | GET | Relevant site role | Filter incident register |
| `/incidents/{id}/acknowledge/` | POST | Operator | Acknowledge with timestamp and attribution |
| `/incidents/{id}/actions/` | POST | Operator/QA | Add corrective action |
| `/incidents/{id}/verify-close/` | POST | QA manager | Quality review / closure |
| `/reports/` | POST/GET | QA/owner/auditor | Create/list generated evidence reports |
| `/subscriptions/` | GET | Owner | Plan and usage state |

**Telemetry example (schema proposal, not public API commitment):**

```json
{
  "device_id": "gw-0001",
  "sensor_id": "temp-001",
  "event_uuid": "c1839695-c120-462a-bef1-48208f542aad",
  "observed_at": "2026-10-20T12:30:00Z",
  "value": -18.2,
  "unit": "degC",
  "sequence": 42892,
  "sensor_status": "ok",
  "firmware_version": "2.0.1"
}
```

**Event topics:** `telemetry.accepted.v1`, `telemetry.rejected.v1`, `sensor.stale.v1`, `rule.breached.v1`, `incident.opened.v1`, `incident.acknowledged.v1`, `incident.resolved.v1`, `notification.attempted.v1`, `notification.failed.v1`, `report.created.v1`. Include tenant id, event id, schema version, occurred_at, correlation id and actor/device id in event envelopes.

**Sample rule pseudocode:**

```text
on new valid sensor reading:
  resolve approved effective rule for sensor zone and observed time
  update window of valid readings, tracking gaps and data quality
  if readings continuously exceed customer-defined bound for duration:
      idempotently open/extend a breach incident
  if readings recover beyond approved hysteresis for recovery duration:
      mark recovery (do not silently close food-safety incident)
  if no valid readings arrive by expected interval plus configured grace:
      open separate data-unavailable incident
  persist rule evaluation, notification attempts and transitions
```

# 10. Non-functional requirements and service levels

These are engineering acceptance targets for a supervised pilot, not initially contractual service-level commitments.

| ID | Domain | Acceptance target / test |
|---|---|---|
| NFR-01 | Availability | >= 99.5% pilot monthly service availability target, excluding agreed maintenance; measured server-side; no guarantee of on-site connectivity |
| NFR-02 | Ingestion | Under normal internet conditions, >= 99.9% of syntactically valid gateway events durably accepted in test; loss and delayed-data accounting demonstrated |
| NFR-03 | Rule latency | 95th-percentile evaluation <= 15 s after valid event is durably received in baseline load test; not end-to-end sensor-to-human response time |
| NFR-04 | UI | 95th-percentile site summary API response <= 2 s for reference tenant dataset; reports asynchronous |
| NFR-05 | Capacity | Pilot load test at 20 sites x 40 probes x one observation/minute (~1.15m observations/day); document resource/financial results |
| NFR-06 | Recovery | Draft RPO <= 15 min for business/incident records; draft RTO <= 4 hours for core cloud services; prove with restore drill |
| NFR-07 | Security | TLS 1.2+, encryption at rest, scoped device identities, mandatory privileged MFA, no high/critical exploitable findings at launch |
| NFR-08 | Audit | Tamper-evident, append-only critical audit event history; log all threshold approvals, escalation changes and support access |
| NFR-09 | Localisation | English and Danish; UTC in storage, customer site timezone in UI/reports with DST test coverage |
| NFR-10 | Accessibility | Aim for WCAG 2.2 AA in customer-facing features, especially alert status and forms |
| NFR-11 | Compliance | DPA and supplier register, privacy policy, incident response, SBOM, risk register and CRA/NIS2 scope assessment before commercial v1 |
| NFR-12 | Quality | Automated unit, integration, load, security and end-to-end alarm-path tests required in CI; manual failover exercises |

**Safety limitation:** A 99.5% SaaS availability target still allows hours of downtime per month; a food operator must retain independent processes and documented contingency monitoring if uninterrupted coverage is essential.

# 11. Security, privacy and operational controls

**Identity:** MFA mandatory for admins and QA approval; login throttling; email verification; step-up authentication for changing critical rules; short sessions; revoke tokens on user removal; immutable support access audit.

**Tenant boundary:** `organisation_id` enforced at every ORM query/API/service event; row-level security where practical; deny-by-default service accounts; tenant context signed when passed through queues; cross-tenant penetration tests and negative tests.

**Devices:** Mutual TLS or individually scoped signed credentials; secure provisioning; certificate/secret rotation and revocation; validate payload timestamps; gateway firmware inventory; trusted updates; physically secure installation; do not expose OT control interfaces.

**Data:** Minimise personal data, pseudonymise event actor in long-lived aggregations where lawful, encrypt in transit and at rest, apply per-tenant retention/data export, maintain subprocessor register, EU hosting preference, DPA and international transfer assessment as applicable.

**Supply chain:** Pin dependencies, SBOM, signed CI releases, SAST/DAST, secret scanning, vulnerability disclosure channel, dependency patch SLAs, third-party component licence review and product boundary analysis under the CRA.

**Notifications:** Multi-provider fallback where commercially justified; provider delivery statuses are not proof of receipt; failed notifications cannot be marked successful. Escalation policy accepted by customer with named on-call staff and periodic route tests.

**Operations:** 24/7 automated observability only initially. A human 24/7 staffed service must not be sold unless staffed, contractually covered, insured and tested. Document support business hours and customer contingency plan.

# 12. UX information architecture and screen requirements

**Primary navigation:** Overview; Sites; Cold Rooms & Sensors; Live Readings; Alerts & Incidents; Corrective Actions; Reports; Energy (P1); Users & Permissions; Integrations; Billing; Settings. Separate SAMSEL operations console with strict support elevation.

**SCREEN-01 – Cross-site overview:** Summarise zone status in words and colour; freshness timestamp; breached/recovering/unknown states; unresolved incidents; trend previews; actionable drilldown. No green indicator for stale data.

**SCREEN-02 – Cold-room detail:** Chart with acceptable range per effective rule; current reading, reading age, sample coverage %, calibration status, sensor and gateway health, current SOP, incidents and direct export.

**SCREEN-03 – Incident centre:** Severity, age, who received attempts, who acknowledged, escalation status, commentary, corrective actions and QA review with an uneditable chronology.

**SCREEN-04 – Rules and approvals:** Draft, test with recorded historical readings, preview estimated alerts, approval with step-up MFA, effective date and revert-by-new-version. Block unapproved critical changes.

**SCREEN-05 – Report builder:** Site/zone/date/incident selection, timezone, missing-data legend, sensor/calibration provenance, PDF+CSV and watermark indicating preliminary vs approved if configured.

**SCREEN-06 – Commissioning checklist:** Gateway registration, sensor mapping, probe placement, test breach, test no-data, notification route, customer sign-off and an explicit activation gate.

**SCREEN-07 – Customer administration:** Users, site scopes, invitations, SSO optional later, billing and export options, DPA links, support approvals and audit views.

Design for desktop industrial QA workflows first, with mobile-responsive incident acknowledgement. Do not rely only on red/green colours, particularly for critical statuses.

# 13. Analytics, calculations and model governance

**Descriptive P0:** Temperature min/max/mean per defined window; count/duration of approved-rule breaches; coverage percentage using expected cadence; device health and data gaps; alert response intervals. Distinguish event timestamp from ingestion timestamp. Document whether metrics use interpolation; do not interpolate unknown readings as actual measurements.

**Energy P1:** kWh and cost by interval where authorised, tariff assumptions recorded, comparison to matched working hours and outside temperature only if reliable data available; savings claim requires pre/post methodology and adjustment for production/weather/operating changes.

**Predictive P2:** Risk signals such as repeated rapid temperature rises, abnormal compressor cycles and persistent night-time energy draw. Only productionise models after pilot dataset, labelled failure examples, false-positive assessment, drift monitoring and human sign-off. Models never execute control actions.

**Quality flags:** `valid`, `out_of_range`, `stale`, `uncalibrated`, `clock_skew`, `duplicate`, `late_arrival`, `estimated`, `imported_manual`. Every report clearly states inclusion rules.

# 14. Testing and acceptance criteria

**Unit:** Rule boundary maths, DST, zero-length readings, dedup, recurrence, hysteresis, severity mapping, log provenance, tenant ID guardrails and SQL indexes.

**Integration:** Simulated gateway telemetry; offline/backfill; failed provider; revoked device; daylight savings change; stale readings; rapid temperature oscillation; overlapping threshold rule changes; CSV ingestion and pdf export.

**Security:** OWASP ASVS-aligned review appropriate to product risk, MFA bypass attempts, IDOR/tenant cross-read tests, malicious gateway payloads, SSRF checks, role matrix, rate limits, audit log tamper resistance and backup encryption.

**Operational drills:** Disconnect gateway and ensure no-data alarm; restart queue and confirm idempotent incident; revoke sensor; test notification retry; restore database and reports; train client on external contingency procedure.

**Customer pilot acceptance pack:** Installation and placement record, sample readings against calibrated reference, approved bounds and contact roster, signed alarm path test, missing-data test, weekly data completeness, support runbook, staff training evidence, contractual SLA limits and customer sign-off.

**Exit criterion:** All P0 acceptance tests pass, no unresolved high/critical security issues, successful backup restoration, measurable notifications and no false-green reading scenarios discovered in end-to-end test.

# 15. Implementation programme and developer epics

Priorities: P0 = must before paid monitored production use, P1 = after pilots, P2 = growth/advanced analytics. Each epic requires its own acceptance tests, migrations, API spec, operational runbook and documentation.

| Epic | Phase | Deliverables | Definition of done |
|---|---|---|---|
| EP-00 Research and governance | Month 1 | Customer journeys, sensor inventory, risk register, data map, signed scopes | Approved requirements + pilot agreements |
| EP-01 Repository/foundations | Month 1–2 | Monorepo, Python/Django, React/TS, Postgres, CI/CD, IaC, environments | Reproducible local/staging deployments |
| EP-02 IAM and tenants | Month 2–3 | Organisation/site roles, MFA, permissions, logs | All permission/negative tests pass |
| EP-03 Asset and commissioning | Month 2–4 | Site/zone/device lifecycle, test checklist | QA signs commissioning record |
| EP-04 Ingestion and durable store | Month 3–5 | MQTT/HTTPS ingestion, validations, duplicate/replay control, raw store | Offline/backfill + load tests pass |
| EP-05 Rules and incidents | Month 4–6 | Threshold rules, no-data, escalation, corrective actions | Alarm failure drills and QA tests pass |
| EP-06 User portal/reporting | Month 4–7 | Charts, dashboards, responsive view, CSV/PDF | Pilot usability and data accuracy checks pass |
| EP-07 Security/reliability | Month 5–8 | Backups, monitoring, pentest, risk/legal reviews, recovery exercises | No unresolved critical findings |
| EP-08 Paid pilot deployment | Month 7–9 | Two customer sites, SOP integrations, training, daily support | Signed site acceptance + KPI review |
| EP-09 Commercial v1 | Month 9–12 | Billing, onboarding automation, service status, SLAs, customer help | 5 paying sites and documented runbooks target |
| EP-10 Energy/enterprise expansion | Month 12–18 | Meter APIs, analytics, SSO, countries | Scoped demand and finance go-gate |

Dates are planning targets from a funded project kickoff; they depend on staffing, data access, sensor choice and regulatory review. Parallel work must not bypass security or site commissioning gates.

# 16. Engineering organisation, governance and delivery

**Suggested product team:** Product owner/domain lead (0.5–1 FTE), experienced backend/IoT engineer (1 FTE), frontend engineer (0.5–1 FTE), DevOps/security support (fractional), QA automation tester (fractional), food-safety domain expert and approved industrial gateway/electrical partner. Smaller teams extend delivery time. Specialist on-call and legal services additional.

**Method:** Two-week sprints; trunk-based development or short-lived branches; coding standards; pull-request review; static analysis and CI; reproducible test fixtures; no production device integration before security review. Demo progress with simulated sensor data to avoid unsafe assumptions.

**Release management:** Dev -> staging -> pilot -> production with release notes, feature flags, reversible migrations where feasible, blue/green or rolling deployment strategy, controlled incident response and rollback playbooks. Require change approval for rule engine and notification changes.

**IP protection:** Development agreements must explicitly assign economic IP rights to SAMSEL, define pre-existing libraries and supplier ownership, allow security audits, require repository and documentation handover, and prohibit vendor lock-in through private unexportable interfaces.

# 17. MVP sprint-level implementation backlog (Codex/developer handoff)

1. **Sprint 1: Foundation.** Define ADRs, monorepo, `docker-compose` dev stack, Postgres migrations, React shell, Django API, CI and basic observability.
2. **Sprint 2: Tenancy.** Models for organisations, sites, memberships and RBAC; verify scoped APIs; email verification and privileged MFA.
3. **Sprint 3: Assets.** Sites, rooms, sensors, devices, commissioning state and calibration metadata; audit baseline.
4. **Sprint 4: Ingestion.** Signed device authentication, HTTPS telemetry, message queue, idempotent durable writers, test telemetry simulator.
5. **Sprint 5: Monitoring.** Readings APIs, freshness/data-quality status, primary dashboard and chart verification.
6. **Sprint 6: Rules.** Versioned thresholds, approval, sustained breach, hysteresis and simulated stale/no-data events.
7. **Sprint 7: Notifications.** Provider adapter, reliable retries/dead-letter queue, escalation chain, notification-attempt records and dry-run.
8. **Sprint 8: Incidents.** Acknowledgement, corrective action, QA closure, immutable timeline and role restrictions.
9. **Sprint 9: Reports.** Auditable PDF/CSV jobs, site timezone handling, data gaps and calibration metadata.
10. **Sprint 10: Reliability.** Load test, penetration test, threat model, backup/restore, multi-tenant negative tests, monitoring and outage drill.
11. **Sprint 11: Pilot integration.** One qualified sensor/gateway connector, on-site commissioning, training and weekly customer feedback.
12. **Sprint 12: Commercial readiness.** Billing plan state, contracts, usage limits, support centre, acceptance pack and remaining incident defects.

**AI coding-agent instruction:** Work one epic/sprint at a time. Do not invent hardware compatibility or law-based food thresholds. Before writing code, print precise scope, models, API contracts, migrations, tests and threat boundaries; request human sign-off for connection to any production industrial device; do not issue control commands. At each sprint finish, deliver migration notes, tests, security checks and a demonstration checklist.

# 18. Dependencies, unknowns and open questions

1. Are the first customers willing to pay DKK 2,950–5,900/month plus onboarding, and for exactly which pain points?
2. Which approved sensor/gateway brands, calibration services and integration protocols will the first sites permit?
3. Are the first sites expecting human 24/7 staffed response rather than technical alerts only?
4. What are the required site/food-specific temperature rules, data frequencies and document retention obligations?
5. Can an authorised customer share useful electricity readings at sufficient resolution? Who pays for meters?
6. Who funds DKK 1.2m–2.5m and signs off staged commitments? Which work is contracted vs performed by founders?
7. Will gateway agents be supplied by SAMSEL, and does CRA apply to those deliverables? Legal review required.
8. What baseline reliability can partner sensors achieve inside actual cold rooms, including battery and signal penetration?
9. What food safety/QA and professional indemnity insurance coverage can be obtained on acceptable terms?
10. Which customer size, support model and price produce genuinely positive site-level contribution margins?

# 19. Source notes and reference documents

Regulation and external evidence sources are referenced in the companion business plan. Primary implementation anchors:

- Danish Veterinary and Food Administration: https://en.foedevarestyrelsen.dk/food/starting-a-food-business-in-denmark/own-checks-in-food-establishments
- Fødevarestyrelsen food storage and transport temperatures: https://foedevarestyrelsen.dk/lovstof/vejledninger/hygiejnevejledningen/26-koelekrav-for-foedevarer
- Energinet ElOverblik official API: https://api.eloverblik.dk/thirdpartyapi/index.html
- European Commission Data Act: https://digital-strategy.ec.europa.eu/en/policies/data-act
- European Commission Cyber Resilience Act: https://digital-strategy.ec.europa.eu/en/policies/cra-summary
- Danish NIS2 Act: https://www.retsinformation.dk/eli/lta/2025/434

**Status of figures and requirements:** Functional requirements, KPIs, technology choices, staffing models and budgets in this document are proposed design targets; they are not claims that SAMSEL has implemented any software or tested any industrial devices. Production use requires qualified installation, customer acceptance and validated legal/security scope.
