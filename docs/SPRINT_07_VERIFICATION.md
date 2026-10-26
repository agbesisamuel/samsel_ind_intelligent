# Sprint 07 verification — 2026-10-21

Local synthetic operation only. Eleven notification behaviors cover personal proof,
expiry/replay, multiple contacts, revoked grants, idempotent scheduling, SMTP failures,
lost leases, escalation/ack separation, maintenance expiry, DST, contingency, raw/API
scope and unsupported production adapter rejection.

| Executed check | Exact result |
|---|---|
| `python scripts/dev.py test` | 124 backend passed in 64.78s; 12 component passed, runner 4.04s |
| `pytest tests/test_notifications.py -q --tb=short` after adding multi-contact regression | 11 passed in 14.17s; total 125 distinct backend cases covered across full and targeted runs |
| `python scripts/dev.py lint` final rerun | Ruff/check format 97 files; Django 0 issues/no migration drift; ESLint/Prettier/types pass |
| `python scripts/dev.py contracts` | Both human/device schemas validate without warnings; generated TS updated |
| `python scripts/dev.py build` | Eleven project images built; frontend 84 modules, JS 375.85 kB/gzip 114.84 kB, CSS 5.69 kB; Vite 475ms |
| `python scripts/dev.py notification-smoke` | Actual local proof/capture and independent dispatcher: 1 accepted attempt, 1 TEST capture, replay no duplicate, 0 new incidents |
| `python scripts/dev.py e2e` | 2 Chromium tests passed in 7.6s; operator reads delivery evidence without route-management/test controls; mobile width passes |
| `python scripts/dev.py secret-scan` | 207 allowlisted source files, 1.31 MB; 0 leaks |
| Compose health | All 13 long-running services healthy, no additional published ports |

Final capture intent: 8b07c24a-8273-42c6-ae48-e57af7c4bf9f. An earlier independent
capture drill also passed (5d5081a0-be83-4348-835b-01e117cc7ba1). Routes were disabled
after each drill; attempts and local mail retained. Mobile screenshot inspected at
output/playwright/notifications-en-mobile.png.

Initial tests caught consumed-token blank validation and FOR UPDATE on a nullable
join. Fixed model metadata with generated /0003 and locked only the notification
row; all affected tests reran. Initial lint flagged long documentation lines; final
lint passed after shortening them. No failing assertion was removed. Applied
notifications/0001 generated schema, /0002 explicit scope/anchor guards and /0003.

Documentation reviewed: code/JSDoc, behavior tests, NOTIFICATIONS/API/README,
deployment/retention/ADR-012/changelog/tracker. No dependencies changed, previous
zero-finding audit baseline retained. Remote CI was updated but not run (no Git or
remote). No production email/SMS, real customer alerts or site activation. SMTP
uncertain outcomes deliberately require investigation; no exactly-once claim.
