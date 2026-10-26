# Sprint 05 verification — 2026-10-21

Local synthetic development only; no production/customer equipment or notifications.

| Executed check | Result |
|---|---|
| `python scripts/dev.py test` | 102 backend passed in 54.30s; 10 component passed, runner 3.46s |
| `python scripts/dev.py lint` | Ruff check/format 77 files, Django 0 issues, no migration drift, ESLint/Prettier/types passed |
| `python scripts/dev.py contracts` | Human/device schemas validate without warnings; generated TypeScript updated |
| `python scripts/dev.py e2e` | 2 Chromium tests passed in 12.9s; actual synthetic graph/raw inspector, mobile width and exact operator site scope |
| `simulate_gateway --count 100` | 100 accepted, 12 rejected, 100 duplicates, 0 pending; actual foreign MQTT topic rejected |
| `python scripts/dev.py build` | Ten project-built images passed; frontend 81 modules, JS 358.25 kB / gzip 110.76 kB, CSS 5.60 kB; Vite 1.01s |
| `python scripts/dev.py secret-scan` | 170 allowlisted source files, 1.03 MB, 0 leaks |
| Compact Compose health check | All 12 long-running services healthy; no additional published ports |

Applied monitoring/0001 generated models and /0002 explicit scope/append-only guards.
Also closed the event-envelope gap found during specification review: telemetry
/0004 adds rejection outbox references/XOR constraint; /0005 adds exact scope and
queues existing rejection metadata without altering it. Both accepted/rejected
events carry stable versioned scope/correlation envelopes, verified against persisted
subjects before consumption. A forged tenant envelope test passes. Historical
Sprint 04 wire format is superseded by this unreleased development upgrade; old
malformed queue bodies remain in private dead-letter storage, not silently deleted.

New deterministic tests distinguish zero/null, missing policy, stale sensor vs
offline gateway, delayed watcher, cadence change, future skew, manual import,
backfill, independent receipt time, QA-only policy approval, immutable evidence,
cross-tenant/raw/aggregate reads and the Copenhagen DST fold. Complete mapped CSV
preview writes no measurements/quarantine; commit rechecks and replay is idempotent.

The first skew test exposed future data updating the heartbeat at the interval
boundary. Fixed the heartbeat window to exclude clock-ahead quality flags, reran
the targeted suite (7 passed), then all regressions and live transports. A screenshot
was inspected at output/playwright/monitoring-en-mobile.png: no page overflow, real
zero displayed, missing original probe remains unknown, timestamps include site offset.

Observed local mixed-workload processing P95 was about 62.65 seconds in the UI.
This includes cold/backlog/restart testing, is not the reference baseline load, and
does **not** establish NFR-03 <=15s. The rules/load/latency targets remain to be
measured and tuned in their relevant sprints. No new dependencies; Sprint 04 audit
remains the unchanged dependency baseline (Python/npm zero known findings).

Documentation reviewed: code/docstrings/JSDoc and behavioral tests; MONITORING,
protocol/API/deployment/retention/decisions/traceability/tracker updated. Generated
artifacts regenerated. Remote CI, real pilot, production load/restore and external
security/legal/domain review not run. No real monitoring activation or food-safety
decision is enabled.
