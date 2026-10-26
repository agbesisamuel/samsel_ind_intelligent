# Security register

| ID | Risk / boundary | Mitigation / evidence | Remaining work |
|---|---|---|---|
| SEC-01 | Cross-tenant disclosure | Sprint 02 exact active grants, scoped queries before pagination, immutable org triggers/composite FKs, T-09 negative matrix | Extend matrix to each new domain, workers, exports and support access |
| SEC-02 | Accidental live operation | Local/test-only settings; no OT adapters, alert delivery or real customer fixtures | Explicit customer/site and deployment approval |
| SEC-03 | Secrets exposure | Generated ignored local .env; encrypted MFA seeds; hashed recovery/reset/invite tokens; redacted errors; source scan | Production secret manager, rotation and reviewed lost-factor recovery |
| SEC-04 | Infrastructure exposure | Loopback published ports; private internal services; session cookies HttpOnly/SameSite; CSRF on unsafe auth | TLS, trusted proxy and hardened production network in Sprint 10 |
| SEC-05 | Unsupported MinIO | RESOLVED in Sprint 01 via pinned stable SeaweedFS 4.48/nginx; S3 isolation verified | Production storage and scoped report access later |
| SEC-06 | Misleading health/safety | Process readiness separate from monitoring; planned sites and explicit no-data screens | No food-safety/SLA/compliance claim |
| SEC-07 | Destructive reset | Local guard and confirmation; reset-demo deletes nothing; seed preserves existing identities/evidence | Any cleanup must target authorized synthetic fixtures and retain audit |
| SEC-08 | Supply chain | Hash locks and pinned images/actions; cryptography 49 advisory found and upgraded to 50.0.2 | Final scan evidence in Sprint 02 report; production SBOM/container scan in Sprint 10 |
| SEC-09 | Account takeover | Invite-only email proof; privileged TOTP; locked replay counters; five-minute step-up; safe recovery/re-enrollment; dynamic session revocation | External penetration review and operational recovery procedure |
| SEC-10 | Audit tampering | Serial hash chain and PostgreSQL UPDATE/DELETE rejection; no raw secret snapshots | DB owner can bypass guards; external anchoring/restricted DB roles/restore proof later |
| SEC-11 | Account mail delivery | Local SMTP only, reset queue through configured app; real auth-smoke; failed mail audited | Account-mail retries/outbox before production; customer notification machinery Sprint 07 |

Evidence: Sprint 01 and Sprint 02 verification reports. Sprint 02 proves the current
identity/site surface, not authorization for domain APIs that do not yet exist.
All real integrations remain **BLOCKED: CUSTOMER/SUPPLIER APPROVAL REQUIRED**.

Sprint 03 extends SEC-01/09/10 with exact-site triple-key constraints, terminal
retirement, append-only qualification and synthetic QA snapshot/currency checks.
A complete synthetic pack cannot activate a live site: rule, route, real acceptance
and environment gates remain explicit. No supported real device profile or actual
calibration/customer sign-off is claimed. Database-owner bypass and production
role separation remain SEC-10 follow-up; normal APIs and bulk writes are tested.

## Sprint 04 local security changes

Per-gateway expiring credentials, exact MQTT publish-only ACLs, signed payloads,
TLS-only device routes, strict payload bounds, current device qualification checks,
append-only measurements and composite tenant/site keys are implemented/tested.
Local CA fixtures are not production PKI. Service-level broker credentials and DB
owner privileges remain production-hardening items; no claim of production assurance.
Broker PUBACK is not application acceptance. HMAC supplements topic ACL enforcement.

## Sprint 10 review

AUTH-03: owner/MFA-approved exact-site diagnostics-only support, 60-minute maximum,
revocation and immutable access logs implemented. No staff data bypass. SEC-10 now
has a restricted runtime SQL role, independent chain verification and encrypted
checkpoint comparison in an actual isolated restore. Infrastructure/database owners
remain trusted; development env sharing is not production secret separation.

SEC-08: Python/npm lock audits and SBOM/licence inventories were executed; available
high/critical Debian fixes applied. CONTAINER_SECURITY.md retains full-image findings
and reachability assessments. Do not equate application audit zero findings with
zero image findings. The final production runtime, all service images, external
penetration test and legal/licence review remain explicit release gates.

The shipped environment refuses production operation. Production PKI, hardened
proxy/cookies/CORS, cloud monitoring/alerts, independent backup custody/PITR and
customer incident responsibilities remain unapproved. Local negative/restore/load
tests cannot certify actual cloud availability, site calibration or food safety.

Sprint 12 adds a narrow platform commercial metadata exception without site access;
current owner/role checks, recent MFA, CSRF/no-store, immutable history/drafts and
formula-safe exports. Quota guards cover concurrent raw SQL and wall-clock expiry
without suspending ingestion. Tickets enforce site/own-request privacy and immutable
evidence. These controls do not resolve Sprint 10 image findings or external gates.
RELEASE_REVIEW.md records no production acceptance or implicit risk waiver.
