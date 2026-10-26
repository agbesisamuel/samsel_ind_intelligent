# Sprint 08 verification — 2026-10-21

Synthetic only; no production/customer/OT actions or food-safety decisions.

| Executed check | Exact result |
|---|---|
| `python scripts/dev.py test` | 137 backend passed in 74.75s; 13 component passed, runner 2.44s |
| Incident targeted suite | Final 12 passed in 12.22s; workflow/QA/replay/scope/encryption/unsafe upload cases |
| `python scripts/dev.py lint` | Ruff check/format 102 files; Django 0 issues/no migration drift; ESLint/Prettier/types pass |
| `python scripts/dev.py contracts` | Human/device schemas validate without warnings; TS regenerated |
| `python scripts/dev.py build` | All 11 project images built; frontend 85 modules, JS 386.81 kB/gzip 117.36 kB, CSS 5.69 kB; Vite 1.35s |
| `python scripts/dev.py evidence-smoke` | Real encrypted private S3 round-trip, plaintext absence and wrong-checksum denial pass; exact test object cleaned |
| `simulate_gateway --count 100` | 100 accepted/12 rejected/100 duplicates/0 pending; actual foreign-topic denial passed |
| `python scripts/dev.py e2e` | 2 Chromium tests passed in 8.2s; incident timeline/upload form, operator cannot QA-close/export, mobile width passes |
| `python scripts/dev.py audit` | Python: no known vulnerabilities; npm: 0 vulnerabilities |
| `python scripts/dev.py secret-scan` | 218 source files, 1.41 MB, 0 leaks |
| Compose health | All 13 long-running services healthy after final recreation |

Transport run 156239db-7ec5-401d-aaf2-5c2aadcd9f18 retained its synthetic spool.
Mobile incident screenshot inspected at output/playwright/incidents-en-mobile.png.
The complete master hash remains unchanged: BE70C9C7B871001AE77D4941A5E06C4F5DD6261A2E8F501DEF0FC84C33B9AB6C.

New SDK dependencies only: boto3/botocore 1.43.116, jmespath 1.1.0, s3transfer 0.19.3;
licences recorded in DEPENDENCIES. Other pins preserved and hashes regenerated.
The first lock output path was root-owned; reran in a writable temporary copy and
copied the generated result back. No hand-edited generated lock. The initial MFA
expiry test used the wrong session field; corrected it to step_up_at, then targeted
and full suites passed. Typecheck required validating unknown JSON before rendering;
fixed with a tested helper. Initial documentation line-length issues were corrected.

Applied incidents/0003 generated fields/attachment model; /0004 identity/immutable/
scope guards; /0005 assignment/current-grant and closure timestamp guards. No source
evidence was deleted. Evidence encryption key was generated into ignored local env,
never printed. Actual S3 SDK conditional write/read/decrypt was verified.

Documentation review: code/docstrings/JSDoc, behavioral tests, INCIDENT_WORKFLOW,
API/ADR-013/dependencies/changelog/privacy/retention/tracker and CI drill. Remote CI,
real hardware/customer acceptance, broader document malware scanning, production
key rotation and external legal/security review remain unrun explicit gates.
