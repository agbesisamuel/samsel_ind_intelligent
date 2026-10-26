# Sprint 02 verification — 2026-10-21

Local Windows/Docker Desktop Linux stack, synthetic data only. Master specification
unchanged (SHA-256 BE70C9C7B871001AE77D4941A5E06C4F5DD6261A2E8F501DEF0FC84C33B9AB6C).
No Git metadata/remote exists, so no commit or remote CI run is claimed.

| Check | Final result | Evidence |
|---|---|---|
| `python scripts/dev.py up` | PASS, exit 0 | Hash-locked images rebuilt with cryptography 50.0.2; migration completed; nine long-running services healthy |
| `python scripts/dev.py test` | PASS, exit 0 | 63 PostgreSQL backend tests (13.67s); 8 component tests (3.17s total runner) |
| `python scripts/dev.py e2e` | PASS, exit 0 | 2 Chromium tests, 4.1s: bilingual/mobile shell and actual operator session/A1 scope/CSRF/logout |
| `python scripts/dev.py contracts` | PASS, exit 0 | OpenAPI validate/fail-on-warn succeeded; generated TypeScript contracts |
| `python scripts/dev.py build` and final `npm run build` | PASS, exit 0 | All images built; final TS/Vite build 78 modules, JS 323.90 kB (101.62 kB gzip), CSS 4.68 kB |
| `python scripts/dev.py smoke` | PASS, exit 0 | PostgreSQL, broker/worker, Redis, storage, SMTP; signed S3 round trip, anonymous/invalid rejection and cleanup |
| `python scripts/dev.py auth-smoke` | PASS, exit 0 | Real RabbitMQ → worker → Mailpit reset; email proof matches stored hash, never printed |
| `python scripts/dev.py audit` | PASS, exit 0 | No known Python vulnerabilities; npm 0 vulnerabilities |
| `python scripts/dev.py secret-scan` | PASS, exit 0 | 112 staged source files, ~552.59 KB, no leaks; local .env excluded |
| `python scripts/dev.py seed-demo` | PASS, exit 0 | Two fictional orgs, separate users/sites and A1-only operator; no credential output |

`python scripts/dev.py lint` PASS, exit 0: Ruff/format (44 files), Django check,
no migration drift, ESLint/Prettier and TypeScript passed.
No tests were skipped. The earlier baseline had 32 tests; two obsolete parametrized
assertions that /me and /organisations did not exist were replaced with the new
protected-route matrix. All remaining foundation safety tests still run.

## Failures found and corrected

- Unsupported/read-only field validation initially used a scalar DRF error; corrected
  to a structured non-field error. Inviter-required fixtures were corrected.
- Fixed-window throttling test crossed a real minute boundary; now uses a deterministic
  clock. Unicode decimal TOTP input now rejects safely instead of raising TypeError.
- OpenAPI needed the custom session scheme and explicit paginated/nested role schemas.
- Windows Vite missed source-change events; restart proved current code, then polling
  was configured for Compose. Host-owned config formatting was applied and image rebuilt.
- Real account mail exposed missing Celery default-app binding. config/__init__ now
  binds the app for HTTP and standalone callers; actual queued delivery passes.
- Python audit's redundant temporary dependency resolution exited without diagnostics.
  Direct scanning of the full pinned transitive lock exposed PYSEC-2026-3552 twice
  for cryptography 49.0.0. Updated to supported stable 50.0.2, rebuilt and reran tests/
  audit. No suppression or unsupported exception was accepted.

## Covered boundaries and limits

T-09: foreign collections/details, query/nested/body spoofing, active membership,
site-only role restrictions, nested role redaction, staff no-bypass, service scopes,
PostgreSQL bulk-write composite FK/immutable ownership. T-22: privileged MFA,
pre-auth expiry, replay denial, step-up expiry/fresh proof, recovery reenrollment,
password-reset MFA retention, role-elevation assurance and session revocation.
Invitation expiry/replay/revocation and existing-account takeover are checked.
Audit hash linkage and database mutation denial are checked. Last-owner retention
and current-role rechecks are exercised. Account mail known/unknown paths are tested.

Documentation review: module/class/function purpose and security invariants, test
behavior docs, generated migration/contract ownership, ADR, API/commands, dependency
versions/licences, privacy/retention/deployment and tracker reviewed. No secrets in
public errors or audit snapshots. Browser preferences contain language only.

Not run: remote GitHub Actions (no Git repo/remote), literal GNU Make (equivalent
Python commands run), production penetration/load/backup-restore/site drills.
No live sensors/customer data/customer alerts/paid providers/production access.
Audit is append-only application evidence, not immune to a database owner; external
anchoring and restricted production DB roles remain later hardening. No monitoring
activation is possible in Sprint 02. Local HTTP is explicit; production stays gated.

