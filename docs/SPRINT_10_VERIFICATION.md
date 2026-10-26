# Sprint 10 — local implementation verified; production acceptance blocked

2026-10-21, Windows / Docker Desktop Linux containers. Master SHA-256 remains
`BE70C9C7B871001AE77D4941A5E06C4F5DD6261A2E8F501DEF0FC84C33B9AB6C`.
No Git metadata/remote exists; no remote CI or production deployment is claimed.

## Implemented

Scoped expiring owner/MFA support grants and immutable access logs; separate
non-owner runtime DB role; API security headers; independent audit-chain verifier;
complete source-bound versioned domain-event receipt transport; encrypted database
and object backup/restore tooling; fixed synthetic reference workload; threat model,
privilege/privacy/retention review, SBOM/licence inventories and image scan register.
Support and events migrations 0001/0002 applied without drift.

Telemetry uses a separate confirmed publisher and 16 fixed gateway queues supervised
in four services. Gateway ordering is retained; queue-modulus upgrades require
draining before switch. ORM hot paths use current qualification subqueries and
DB-guarded narrow projection writes. Unchanged rule decimals now serialize identically
before/after DB reads; integer fixture inputs previously produced stale approvals.
Storage capacity is bounded at 32 sparse volumes of 128 MiB, preserving existing
data; the previous eight-slot limit could not allocate a smoke collection alongside
application evidence. Probe failures now identify the operation without sensitive
response bodies. Repeated authenticated storage smoke checks passed after the fix.

## Completed checks

- Full `test`: **152 backend passed in 118.44s**, **13 components in 4.62s**.
- Final targeted shard routing/supervision/partial-start cleanup: **6 passed in
  36.00s** (155 total unique backend cases across full and targeted runs).
- Existing Chromium browser checks: **2 passed in 25.4s**.
- Final Ruff/format (**133 files**), Django checks/migration drift and
  ESLint/Prettier/types passed. All 17 buildable service images and frontend bundle
  built successfully. Final non-root frontend: **13 component tests in 7.18s**,
  lint/types/build passed, **2 browser tests in 10.9s**.
- Contracts regenerated successfully after renaming a colliding support input schema.
  Initial duplicate `ApprovalInput` warning correctly failed the strict generator.
- Frontend build passed: 86 modules, JS 390.95 kB (gzip 118.49), CSS 5.69 kB (gzip 1.92).
- Runtime role: three forbidden SQL operations denied; no superuser/DDL/role creation;
  API security headers and audit chains verified. Corrupt/wrong-key backups rejected.
- Python/npm audits: **0 known application dependency findings**; source scan:
  **266 files / 1.62 MB, 0 leaks**. This is distinct from container findings.
- Actual TEST notification smoke: one capture/attempt, no fabricated incident.
- PDF/CSV report smoke: actual independent worker, encrypted storage, checksum and
  scoped download grants passed (jobs `3e31f345-ee6c-40c3-a47f-cfebee40819f` and
  `ad3c118c-3550-4dde-9430-56537482f195`).

The first targeted test launch overlapped an API readiness restart and did not run;
the sequential readiness/test/schema rerun passed. No assertion was weakened.

## Actual isolated recovery

`restore-drill` restored **3,940 readings, six objects/artifacts and four audit
chains** in new containers, isolated internal network, **zero published ports**.
RTO **28.4293503 seconds**; latest-restored-audit age at simulated failure
**438.312628 seconds**; checkpoint age at completed verification **36.326412 seconds**.
Quiet business time is included in audit age; it is not measured data loss.
Encrypted bundle: 4,087,160 bytes, SHA-256
`d13290568ac5f1d41fc37b0969174889bfb4b47308dc0dacd8d170006020ed7f`.
Evidence `.artifacts/restore-82ce4dea90f844fbac294a0e34ed65c3/result.json`.
Manual local snapshot/drill meets these measured timing targets; scheduled cloud
backup/PITR and production RPO remain unproven. See RECOVERY.md.

## Performance evidence and corrections

All runs offered 20 sites × 40 probes × one observation/minute for three real
cadence rounds, 2,400 measured TLS HTTPS submissions. All raw results are retained.

| Run | Accepted / processed / pending | Processing P95 | Dashboard P95 | Alerts | Interpretation |
|---|---|---|---|---|---|
| `872b4086…` | 2400 / 2400 / 0 | 126.609921s | unmeasured | none | Initial serial baseline failed throughput/latency; 287.46s send time |
| `0e9ed94c…` | 2400 / 2400 / 0 | 20.354112s | 0.080470s | 0 | Four shards; integer snapshot mismatch excluded all rules |
| `59460aa9…` | 2400 / 2400 / 0 | 3.057688s | 0.090269s | 72 at collection | Rules fixed, separate publisher; early fixture cleanup raced final planner work |
| `9efe9afd…` | 2400 / 2400 / 0 | 24.090350s | 0.207334s | 80 / 80 | Complete alert proof, but four-shard latency was not repeatable |

Final 16-shard run `f6fefcc1-1133-408f-9880-5efe8f3c1175`: **2,400 accepted /
2,400 processed / 0 pending**, **100% durable acceptance**, zero rejected/errors/
duplicates, processing P95 **2.057935s**, dashboard P95 **0.203849s** (20 samples),
**80/80 TEST notifications**, observation-to-capture P95 **10.871798s**. Send elapsed
180.099786s; 13.325946 completed receipts/s. NFR-02/03/04 short local baseline gates
passed. Evidence `.artifacts/reference-load-16-shards.json`.
Initial results are not discarded or
presented as a 24-hour soak. No observed sample is invented to fill a gap.

The nominal cadence is 13.333 observations/s (1,152,000/day); finite-run receipt
throughput includes final request completion time. Docker sample during the four-
shard run: PostgreSQL 184.90% CPU / 138.7 MiB, device API 155.59% / 227.6 MiB;
four consumers together 182.06% / ~327 MiB, publisher 12.38% / 79.09 MiB. These are
one-time local samples, not host averages or cloud sizing guarantees.
Docker reports **14 CPUs and 16,506,826,752 memory bytes** available to this local
engine; results must not be assumed for a smaller CI/cloud runner. Raw table plus
indexes grew about 3.1 MB per 2,400 readings (~1.5 GB/day extrapolation), excluding
WAL, replicas, audit, backup and report growth. No cloud account or bill exists;
monetary cost-to-serve requires approved hosting/provider/support assumptions.

## Security/release gates

Actual producer run `514d3fab-b4da-4e26-aaa8-202f1ca3be04` overlapped a controlled
restart of all four telemetry groups and publisher: **1,000 accepted, 12 malformed
rejected, 100 duplicates, 0 pending; foreign MQTT topic denied**. Persistent SQLite
spool and durable queues/outbox retained across restart; raw/backfilled history was
preserved. This drill proves recovery/deduplication, not the baseline latency target.

SBOMs and declared licence metadata retained under `.artifacts/security/`; 82
installed Python distributions have licence declarations. Node inventory includes
MIT/ISC/Apache/BSD/MPL/CC/BlueOak/Python licence families; legal/native/transitive
licence review remains open. Available Debian high/critical fixes applied; second
API scan still has **2 critical / 65 high** package findings. See
CONTAINER_SECURITY.md for explicit reachability analysis and production gates.
All eight image families scanned; exact counts/reachability limitations are in
CONTAINER_SECURITY.md. No full-fleet zero-finding claim or production security
acceptance is made. An interrupted advisory download was resumed from the valid
shared cache; an obsolete Compose image-index reference was replaced by resolving
the service's configured image ref. Final scans completed successfully.

Production settings reject operation. Cloud availability/operational paging,
external expert penetration test, legal/privacy/licence review, independent key/
checkpoint custody, actual site/hardware/QA acceptance and customer continuity
procedures are explicit human release gates. No real equipment, customer data,
live recipients, paid sends or production deployment was used.
