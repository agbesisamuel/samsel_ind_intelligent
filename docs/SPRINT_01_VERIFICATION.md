# Sprint 01 verification — 2026-10-21

Windows / Docker Desktop Linux, Docker 29.8.0, Compose 5.5.1. Containers:
Python 3.13.12, Node 24.22.0, PostgreSQL 17.11. Host browser tooling:
Node 24.16.0 / npm 11.13.0. No SQLite substitution, real customer data or equipment.
Historical initial run: functional acceptance passed; overall was **PARTIAL** for
archived MinIO support (SEC-05). That exception is now resolved by ADR-006 and
`SPRINT_01_STORAGE_VERIFICATION.md`. Results below retain the original run evidence.

## Commands actually executed

| Command | Result | Exact observed outcome |
|---|---|---|
| `python scripts/dev.py setup` | PASS, exit 0 | Unique ignored .env created; repeat preserved it |
| `docker compose config --quiet` | PASS, exit 0 | Valid configuration |
| `python scripts/dev.py up` | PASS, exit 0 | Builds, migration, all eight services healthy with --wait |
| `python scripts/dev.py migrate` | PASS, exit 0 | Initial migration applied at startup; repeat: “No migrations to apply” |
| `python scripts/dev.py test` | PASS, exit 0 | Pytest **25 passed**, 10.75 s; Vitest **5 passed**, 5.97 s |
| `python scripts/dev.py lint` | PASS, exit 0 | Ruff lint/format: 26 files; Django: 0 issues; no migration changes; ESLint/Prettier/TypeScript pass |
| `python scripts/dev.py build` | PASS, exit 0 | All five container build targets; Vite 74 modules, 1.05 s bundle build |
| `python scripts/dev.py contracts` | PASS, exit 0 | OpenAPI 3.1 validation with fail-on-warning; TS generation; before/after SHA-256 identical for all contract files |
| `python scripts/dev.py smoke` | PASS, exit 0 | PASS database, broker/worker, cache, storage, smtp |
| `python scripts/dev.py audit` | PASS, exit 0 | pip-audit: no known vulnerabilities; npm audit: 0 vulnerabilities |
| `python scripts/dev.py secret-scan` | PASS, exit 0 | Gitleaks: 0 leaks; 78 source files / 276,660 bytes; no local credentials mounted, no scanner network |
| `python scripts/dev.py e2e` | PASS, exit 0 | Chromium **1 passed**, 5.6 s final run against actual Compose stack |
| `python scripts/dev.py seed-demo` | PASS, exit 0 | Explicit no-op; no Sprint 01 domain records |
| `python scripts/dev.py reset-demo --confirm-local` | PASS, exit 0 | Guarded no-op; non-local/unconfirmed refusals tested |
| `docker compose ps --format json` | PASS, exit 0 | API, worker, web, PostgreSQL, RabbitMQ, Redis, MinIO, SMTP running/healthy |

Bundle: HTML 0.53 kB; CSS 4.07 kB (1.43 kB gzip); JS 306.13 kB (96.68 kB gzip).
These are build results, not performance/SLA evidence. Make recipes invoke the same Python runner.

## Coverage and visual review

- Four account tests: UUID/email/unusable password; case-insensitive uniqueness on
  bulk insert; empty-email rejection; inconsistent superuser flags.
- Eleven HTTP/permission cases: minimal health/correlation/security headers, real DB
  readiness, outage redaction, four absent domain paths, two staff/user default-deny
  cases, read-only probe and generated contract surface.
- Ten safety cases: four refused deployment environments, four refused reset
  environments, inherited production override and missing reset confirmation.
- Five component tests: no fake readings, failed API and retry, Danish/English keys
  and persistence, honest auth stub, unknown-route recovery.
- One Chromium flow: actual API proxy, English missing-data state, keyboard skip link,
  Danish/reload persistence, unavailable route and 390 px viewport without page overflow.
- Infrastructure: SELECT 1; authenticated AMQP + actual worker ping; authenticated Redis
  PING; MinIO readiness; SMTP NOOP. No business event, object or email created.

Captured and visually inspected `output/playwright/overview-en.png` and
`output/playwright/users-da-mobile.png`. No clipping/page overflow observed.
This is not a full WCAG or assistive-technology audit.

## Failures corrected during implementation

1. Initial sandbox Docker access denied; approved local engine access enabled testing.
2. ESLint 9 reported unsupported; updated to stable 10.13.0 and compatible tooling.
3. Premature host migration ran before Django installation finished; rerun generated
   migration/schema. Host generation warned about unavailable Docker-only `postgres`
   DNS; real migration/history checks later passed inside Compose.
4. Ruff found formatting/docstring/import-order issues; fixed and explicitly configured
   first-party module ownership for identical host/container behavior.
5. RabbitMQ 4.3 rejected Celery's default transient non-exclusive control/event queues;
   enabled supported exclusive ephemeral queues while retaining durable task queues.
   Actual worker ping and full-stack checks pass; no deprecated broker override.
6. A lint run was interrupted by container replacement; rerun after startup passed.
7. Automatic approval review rejected the full-repository scanner mount because it
   included .env. Source-only staging, pinned image, no network, read-only access and
   dropped capabilities were approved; scan passed. No permission request remains blocked.
8. Schema generation writes to container-owned /tmp and copies out to avoid Linux
   bind-mount ownership failures for the non-root API; exact regeneration check passed.
9. An additional one-off CI YAML check incorrectly asserted 16 steps and failed;
   the workflow has 15 steps. Corrected structural validation passed: required
   top-level keys and exactly one action/command per step. This is syntax/structure
   checking only, not remote GitHub Actions execution.

## NOT RUN / not achieved

- Remote GitHub Actions: no Git metadata/remote. Pinned-action workflow supplied;
  equivalent local Linux-container checks actually executed.
- Literal GNU Make: not installed. Exact Python recipes executed; Ubuntu CI has Make.
- Full T-01..T-22 customer/tenant/monitoring scenarios, load, restore and field drills:
  later sprints, missing implementations/authorized sites. Default-deny tests are
  not claimed as comprehensive tenant isolation proof.
- Independent penetration testing, container/MinIO Go dependency scanning, legal/licence
  approval, production certification, non-Chromium matrix and full accessibility audit.

## Demonstration and file changes

Open http://127.0.0.1:5173; confirm local-only warning, API reachable and no monitoring
data; switch Dansk and reload; open Users & permissions and confirm unavailable/signed
out; use keyboard skip link and narrow layout. `down` preserves volumes when finished.

| Files/directories | Delivered behavior |
|---|---|
| `apps/api/config/`, `sii/accounts/`, `sii/common/`, `manage.py` | Local/test settings, WSGI/ASGI/Celery, UUID identity, probes/errors/default deny |
| `apps/api/sii/accounts/migrations/0001_initial.py` | Generated initial identity schema/constraints |
| `apps/api/tests/`, `pyproject.toml`, `requirements.lock` | PostgreSQL tests, safety cases, lint/docstrings, hashed dependency lock |
| `apps/web/src/`, tests and package/config files | Responsive bilingual shell, typed API query, unavailable routes, component/E2E tests, build/type/lint and lock |
| `compose.yaml`, `infra/docker/` | Eight local services + migration; pinned images and MinIO source build |
| `scripts/`, `Makefile`, `.env.example` | Portable commands, safe secret scan, infra checks, placeholders |
| `.github/workflows/ci.yml`, `.gitleaks.toml`, ignore/attributes files | CI/scanning baseline and reproducible source boundaries |
| `packages/api-contracts/` | Generated OpenAPI/TypeScript and regeneration instructions |
| `packages/event-contracts/`, `simulator/gateway/` READMEs | Future-sprint boundaries only |
| `README.md`, `AGENTS.md`, `docs/` | Setup/demo, maintainer docs, ADRs, versions/licences, progress/security/operations |

Original master and `srs/` preserved. No Sprint 02 implementation started.
