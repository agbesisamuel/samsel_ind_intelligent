# Sprint 06 verification — 2026-10-21

Local synthetic development only. No customer equipment, live notifications or
food-safety decisions. Twelve new rule cases exercise deterministic sustain/gaps,
jitter/hysteresis, recovery, retry, independent failures, maintenance, scope/SQL
immutability, QA independence, full API lifecycle and superseded late input.

| Executed check | Exact result |
|---|---|
| `python scripts/dev.py test` | 114 backend passed in 47.71s; 11 component passed, runner 3.38s |
| `python scripts/dev.py lint` | Ruff/check format 87 files; Django 0 issues, no migration drift; ESLint/Prettier/TypeScript pass |
| `python scripts/dev.py contracts` | Both human/device schemas validate without warnings; generated TS updated |
| `python scripts/dev.py build` | All ten project images built; frontend 83 modules, JS 367.43 kB/gzip 112.79 kB, CSS 5.69 kB; Vite 601ms |
| `python scripts/dev.py e2e` | Final 2 Chromium tests passed in 6.5s; operator rule read-only view, exact site scope and mobile width |
| `simulate_gateway --count 100` | 100 accepted, 12 rejected, 100 duplicates, 0 pending, actual foreign MQTT topic denied |
| `python scripts/dev.py secret-scan` | 190 source files, 1.18 MB; 0 leaks |
| Compose health | All twelve long-running services healthy after API/telemetry/freshness restarts |

The initial browser run began before the restarted API listened and failed both
tests. Vite recorded ECONNREFUSED at 01:00:24 UTC; Django started at 01:00:25.
After confirming readiness, the complete browser rerun passed. No application
assertion was weakened. Browser screenshots remain under output/playwright/.

Applied generated rules/0001 and incidents/0001..0002, plus explicit rules/0002
tenant/site FKs and append-only guards. The worker evaluates and marks durable work
complete in one transaction. Actual transport run:
ff4df9a3-aab4-4e3e-a515-a00439b84ec6; spool retained in the private simulator volume.

Documentation reviewed: module/class/function docstrings, JSDoc, behavior tests,
RULES/API/ADR-011/traceability/changelog and tracker. Contracts/migrations are
generator-owned except the documented SQL guard. No dependencies changed; previous
zero-finding dependency audit remains the baseline. Remote CI, qualified rapid-change
profile, real customer QA/site approval and production/reference-load proof were not
run or claimed. Human incident workflow and notifications are subsequent sprints.
