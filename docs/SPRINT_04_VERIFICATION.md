# Sprint 04 verification — 2026-10-21

Windows / Docker Desktop Linux, local synthetic database only. No Git repository or
remote CI exists. Master specification preserved. No customer/hardware/live alerts.

| Executed check | Exact result |
|---|---|
| `python scripts/dev.py test` | 94 backend passed in 37.48s; 9 component passed, runner 3.19s |
| `python scripts/dev.py lint` | Ruff check/format (69 files), Django system check (0 issues), no migration drift, ESLint/Prettier and TypeScript passed |
| `python scripts/dev.py contracts` | Human and dedicated device OpenAPI validated without warnings; TypeScript regenerated |
| `docker compose exec -T device-api python manage.py simulate_gateway --count 1000` | 1,000 accepted, 12 malformed/spoofed rejected, 100 duplicates, 0 pending; 500 HTTPS + 500 MQTT |
| Worker restart during that workload | Restarted with accepted data pending; all 1,000 processed, no duplicate measurements; outbox dead count 0 |
| Follow-up simulator `--count 100` | 100 accepted, 12 rejected, 100 duplicates, 0 pending, foreign MQTT topic rejected by actual broker |
| `python scripts/dev.py build` | All nine project-built images passed; frontend 80 modules, JS 339.71 kB / gzip 105.71 kB, CSS 4.95 kB; Vite build 1.90s |
| `python scripts/dev.py audit` | Python: no known vulnerabilities; npm: 0 vulnerabilities |
| `python scripts/dev.py smoke` | Database/broker/cache/storage/SMTP passed; signed S3/anonymous/invalid denial and round-trip cleanup passed |
| `python scripts/dev.py e2e` | 2 Chromium tests passed in 13.5s; English/Danish, exact A1 access, mobile inventory and logout |
| `python scripts/dev.py secret-scan` | 154 allowlisted source files, 919.22 KB, 0 leaks |

Additive migrations applied: assets/0004 engineering capability metadata;
telemetry/0001 generated models, /0002 documented SQL scope/append-only guards,
/0003 gateway UUID receipt uniqueness. Existing data/identity/audit preserved.

Run evidence: simulator UUID `3311cb84-e929-4787-b26a-e17c0ea879d5` (1,000),
`d12c6208-883b-440c-8ed0-cc93c6bd6cfd` (100). SQLite spools are retained on the
simulator-data volume. No credentials were printed or stored in spools.

Failures found and fixed: initial strict TLS verification required AKI/SKI/key-usage
extensions; corrected generator uses new v2 volumes and preserves initial unused
volumes. Explicit device settings in Compose avoid the shared Celery bootstrap
selecting human URL configuration. Schema name collision was renamed rather than
suppressing schema warnings. One secret-scan false positive matched the empty
trusted-proxy option beside `--keyfile`; multiline YAML removed ambiguity without
adding an ignore rule. A broker recreation temporarily disconnected the consumer;
restart policy recovered after topology bootstrap and the full workload passed.

Documentation review: new/modified modules and public functions have purpose,
failure, provenance and authorization documentation; tests explain protected
behavior. Protocol, ADR-009, dependencies, API/deployment/privacy/retention and
tracker updated. Generated contracts/migrations use documented generators.

Limits: no production PKI, real adapter, customer site, paid send, remote CI,
production scale/restore proof or external pen test performed. CSV is the allowed
Sprint 04 baseline (format preview and domain validation on commit); complete
mapping/preview belongs to Sprint 05. Broker PUBACK is not an application receipt.
No threshold/rule, live monitored site or food-safety decision is enabled.
