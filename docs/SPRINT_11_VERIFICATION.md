# Sprint 11 — simulator/pilot-ready branch verified

**BLOCKED: no authorised hardware/site.** No supplier-approved real profile or
customer access agreement exists. The master's explicit fallback branch is used;
zero physical pilot sites or professional/customer sign-offs are claimed.

Implemented a read-only Sample/Profile/Adapter SDK, persistent gateway-bound FULL-
commit replay buffer with source-clock/sequence preservation and durable receipt
validation, separate outage metadata and actual local TLS SDK drill. Added scoped
readiness and immutable synthetic daily/weekly reviews with server-derived health/
queue/report snapshots, actor/time, SQL tenant/immutability/provenance guards,
bilingual integration UI and commissioning/route links. Synthetic records and
configuration cannot activate customer monitoring. No application dependencies added.

Commands/results, 2026-10-21:

- `test`: **162 backend passed in 70.30s**, **14 components in 5.33s**.
- Final adapter tests after a bulk forged-real-provenance check: **7 in 12.76s**.
- `lint`: Ruff/format **141 files**, Django check, migration drift, ESLint/Prettier
  and TypeScript passed. Generated adapters/0001 and SQL /0002 applied; no drift.
- Strict `contracts` passed. Initial enum-name collision failed correctly; shared
  ReviewKind/schema override fixed it. Generated files were regenerated, not edited.
- `build`: all 17 buildable service images and frontend passed; 87 modules,
  JS 394.64 kB (gzip 119.42), CSS 5.69 kB (gzip 1.92), bundle 1.62s.
- `e2e`: **2 Chromium tests passed in 13.7s**, including exact A1-only scope,
  English/Danish hardware blocker and no automatic go-live. Mobile screenshot
  `output/playwright/integrations-da-mobile.png` visually inspected; readable labels,
  controls and blocker without viewport overflow.
- `adapter-smoke`: **3 buffered/accepted, 3 duplicates, 0 pending**, real local TLS
  with spool close/reopen, source zero and disconnect metadata. Run
  `af11cd9b-747e-4912-b54d-26e56ade703a`; credentials revoked, spool/history retained.
- Python/npm lock audits: **0 known findings**; Gitleaks **282 source files /
  1.69 MB, 0 leaks**. Sprint 10 image remediation/review gates remain open.

Manual demonstration: setup/up/migrate/seed-demo; open `/integrations` as a granted
user, inspect the blocker/profile/counts, use Inventory's commissioning pack and
Notifications' TEST routes. An operational user with recent MFA can append a
synthetic daily/weekly review; it appears in preserved history and cannot enable
live use. Change locale; logout/revoke scope prevents further site requests.

NOT RUN: real adapter/vendor qualification, physical placement/calibration,
customer agreement/training/sign-off, two supervised pilot sites, live alerting,
cloud deployment and production operational/security/legal acceptance. These need
separate explicit authorization and qualified personnel. SDK source/regeneration,
failure modes, privacy, immutable history and commissioning documentation reviewed.
