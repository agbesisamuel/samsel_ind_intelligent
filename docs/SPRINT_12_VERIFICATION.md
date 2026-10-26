# Sprint 12 — local commercial/support verification

Local software implemented; production release remains **BLOCKED**. No actual
customer/site pilot, security/legal/food-safety approval, paid provider, live
collection or production deployment is claimed. P1/P2 have not been started.

Implemented BILL-01/EP-09: immutable technical catalog/default subscriptions,
transactional API/SQL quota guards, wall-clock expiry, non-destructive downgrade,
seven-day warnings, owner billing contacts, platform/MFA term history and immutable
idempotent manual draft/CSV. Commercial expiry leaves existing ingestion intact.
Added scoped immutable support conversations, operator privacy, onboarding/usage/
production blockers and export-authorized bounded acceptance references. Bilingual
Billing/Help and current-role Integrations navigation use generated contracts.

Migrations: generated billing/0001, support/0003; owned documented SQL billing/0002,
billing/0003 and support/0004. Runtime plan DML is explicitly revoked. Schema, model
and generated contract changes are reviewable; no generated artifacts were patched.
No application dependencies changed; exact supported pins/hashes remain documented
in DEPENDENCIES.md and committed Python/npm locks/image references.

Commands executed on 2026-10-21 (Python dev command equivalents of Make):

- `test`: **170 backend passed, 169.66s; 14 components passed, 7.53s**.
  Eight new backend cases protect API/raw/concurrent quota writes, archive/unarchive,
  expired-term ingestion, wall-clock expiry, finance scope/history/idempotence/CSV,
  immutable tickets/revisions, operator privacy and independent incident closure.
- `lint`: Ruff/format **148 files**, Django check, migration drift, ESLint/Prettier
  and TypeScript passed on final run. Initial billing-history timezone typo failed
  TypeScript, corrected to timezone_default; an overlapping container recreation
  interrupted a lint exec, then the complete command passed after startup.
- `up`: all 17 buildable service images built; all long-running services healthy;
  migrations/transport initialization exited successfully, no source volumes deleted.
- `contracts`: human/device strict OpenAPI validation and generated TypeScript passed.
- `build`: all 17 images plus frontend passed; **89 modules**, JS **414.68 kB**
  (**124.34 gzip**), CSS **5.75 kB** (**1.93 gzip**), bundle **6.79s**.
- `e2e`: **2 Chromium tests passed, 31.4s**, against actual local services. Includes
  exact A1 scope, denial of operator billing/exports, Danish production blocker/help,
  actual support creation/reply/resolution and logout/cookie/CSRF checks. Inspected
  `output/playwright/help-da-mobile.png`; readable at 390px without viewport overflow.
- `commercial-smoke`: genuine password/TOTP HTTP flow, idempotent zero-value manual
  draft, owner CSV export and platform site-data denial passed. Retained invoice
  `dafbdbff-234d-4677-ac8a-d2401f29c653`; fictional drill identities disabled in finally.
- `smoke`: database, broker, Redis, SMTP and storage passed; actual authenticated
  S3 round trip, anonymous/invalid denial and own-object/bucket cleanup passed.
- `adapter-smoke`: **3 accepted, 3 duplicates, 0 pending**, real local TLS and spool
  reopen; run `dbd936ca-cc93-4fe7-9b11-5fe807124e71`, credentials revoked/history retained.
- `security-check`: **4 forbidden runtime SQL operations denied**, no owner/DDL or
  plan DML rights; non-root, CapEff=0, NoNewPrivs=1, API security headers and complete
  audit chains passed; 82-package inventory; backup corruption/wrong-key tests passed.
- `audit`: Python/npm locks **0 known application vulnerabilities**. This does not
  supersede unresolved full-image findings in CONTAINER_SECURITY.md. No dependencies/
  base packages changed; the eight-image Sprint 10 scan was not represented as a
  new scan of final source-layer image digests or as production sign-off.
- `secret-scan`: 302 source files / 1.88 MB, **0 leaks**, before final report edits;
  final documentation scan recorded below.

Load initial run `77331cc9-b390-4477-ae96-3f7c6c601fd3` FAILED correctly:
2,400 accepted/processed, 0 pending/errors, processing P95 3.127536s and dashboard
P95 0.0998124s, but sender took 355.053783s (6.75954 receipts/s), source latency
caused 978 late-backfill classifications and 0/80 TEST notifications. No safety
classification was weakened. Device ingress increased from two to four Gunicorn
processes; benchmark now explicitly rejects cadence above 3*60+30s or late readings.
Retained `.artifacts/reference-load-sprint12.json`. Final repeat/restore pending.

Corrected development failures: transaction-test flush removed catalog fixtures;
test-only reseeding uses the owned migration source without disabling SQL guards.
An incomplete synthetic sensor fixture failed NOT NULL before the quota race; adding
its required cadence and a successful serial preflight made the intended concurrent
capacity test meaningful. The race now accepts exactly one competing SQL insert.
Global error redaction is preserved; the quota API test uses a positive identical
payload after increased allocation rather than depending on private error text.
An imported role model needed restoring after test expansion; a fresh full run passed.

Manual demonstration: setup/up/migrate/seed-demo; owner `/billing` shows server usage,
technical templates/contact controls and immutable term/draft history. Operator
direct `/billing` denies access. At `/help`, select a granted site, inspect failure/
unknown counts, release gates, onboarding and current ticket scope; submit fictional
text and append a reply/status. Resolve support and confirm safety incidents remain
unchanged. Export-capable roles inspect archive metadata and use original report
authorization; owners may approve bounded recent-MFA diagnostics-only support.
Switch Danish/English and revoke/logout to verify access changes. See COMMERCIAL.md,
OPERATIONS.md and CUSTOMER_TRAINING.md for maintained handover and responsibilities.

Documentation review covers purpose/security docstrings/JSDoc, behavior tests, owned
SQL invariants and regeneration workflow. Remote CI and literal GNU Make are NOT RUN
(no Git/remote, Windows Python equivalents used). No actual 24-hour soak, cloud pager/
PITR, customer data, physical calibration/training or external sign-off was performed.
RELEASE_REVIEW.md lists blockers and evidence needed for a separate human go/no-go.
Master source remains unchanged. Stop after Sprint 12; no post-MVP work is authorized.
