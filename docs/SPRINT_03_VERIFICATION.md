# Sprint 03 verification — 2026-10-21

Local synthetic stack only; no new dependencies or hardware/customer access.
The master remains unchanged. Sprint 02's security and tenant foundation is retained.

| Check | Final result |
|---|---|
| Full `python scripts/dev.py test` | PASS, exit 0: **78 backend tests**, 48.65s; **9 component tests**, 7.13s runner |
| `python scripts/dev.py e2e` | PASS, exit 0: **2 Chromium tests**, 13.3s; real A1-only operator inventory, unknown calibration, blocked activation, no edit controls, mobile width and logout |
| `python scripts/dev.py lint` | PASS, exit 0: Ruff/format 50 Python files, Django check, no migration drift, ESLint/Prettier and TypeScript |
| `python scripts/dev.py contracts` | PASS, exit 0: schema validation/fail-on-warn, regenerated TypeScript |
| `python scripts/dev.py build` | PASS, exit 0: all images and final frontend; 80 modules; JS 339.71 kB (105.71 kB gzip), CSS 4.95 kB |
| `docker compose up -d --wait --wait-timeout 300` | PASS, exit 0: nine healthy long-running services and successful migration job |
| `python scripts/dev.py smoke` | PASS, exit 0: DB, RabbitMQ/worker, Redis, storage, SMTP, authenticated/negative S3 lifecycle/cleanup |
| `python scripts/dev.py secret-scan` | PASS, exit 0: 125 staged source files, ~794.92 KB, no leaks |
| `python scripts/dev.py seed-demo` | PASS, exit 0: planned synthetic inventory added idempotently; no fabricated calibration or approvals |

No dependency versions changed; Sprint 02's Python/npm 0-known-vulnerability audit
remains the dependency baseline. No new package/image exception was introduced.

The 15 added PostgreSQL asset tests cover all nine foreign inventory/evidence
collections, foreign/same-tenant wrong-site IDs, scope/state/actor mass assignment,
calibration unknown/current-synthetic/expiry/future rejection, QA separate from
owner, terminal retirement, T-20 activation rejection, complete synthetic acceptance,
snapshot preservation/currency after configuration changes, bulk cross-site FKs,
immutable source identity and append-only evidence. Existing T-09/T-22 tests rerun.

During implementation, schema lifecycle enum naming and a TypeScript union access
were corrected. One full test run was interrupted by container recreation; the
final complete run above succeeded after services stabilized. No skipped tests or
unresolved check failures. Narrow inventory screenshot retained under output/playwright.

Documentation review completed: modules/classes/functions/JSDoc and meaningful test
docs, generated migrations/contracts workflow, explicit SQL guard ownership, API,
commissioning, credential design, ADR-008, README, security/privacy/retention,
deployment and traceability. Metadata/evidence use UTC and site-timezone display.

Not claimed/run: remote CI (no repository/remote), real hardware compatibility,
physical calibration, actual customer acceptance, production activation, later
telemetry/rules/alerts/reports/load/restore proof. All local QA evidence is synthetic.
Active monitoring remains blocked by missing verified rules/routes/real acceptance
and local environment. Database owners can bypass guards; production role separation
and external audit anchoring remain scheduled hardening.
