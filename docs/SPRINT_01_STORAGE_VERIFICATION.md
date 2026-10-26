# Sprint 01 storage support resolution — 2026-10-21

Scope: resolve SEC-05 only, under the user's explicit follow-up request. ADR-006
supersedes the initial MinIO selection. SeaweedFS 4.48 and nginx 1.30.6 are current
stable maintained releases, pinned by tag and registry digest. The master document
and Sprint 02 code scope are unchanged. This is local synthetic development,
not production storage approval or complete tenant authorization.

Environment: same Windows/Docker Desktop Linux setup as the initial verification
report; Python 3.13.12 containers. Backend image reports SeaweedFS revision
`530be3e37`, Alpine 3.24.2, curl 8.22.0. No new Python/npm dependencies.

## Executed checks

| Command / operation | Result | Observed outcome |
|---|---|---|
| `python scripts/dev.py setup` | PASS, exit 0 | Existing values retained; missing local S3 keys generated without printing them |
| `docker compose config --quiet` | PASS, exit 0 | Final Compose config valid |
| `docker compose up -d --remove-orphans --wait --wait-timeout 300` | PASS, exit 0 | MinIO container retired; old volume preserved |
| Final `docker compose up -d --wait --wait-timeout 120` | PASS, exit 0 | Nine services healthy; migration completed |
| `python scripts/dev.py test` | PASS, exit 0 | **32 backend tests in 8.33 s; 5 component tests in 5.52 s** |
| `python scripts/dev.py lint` | PASS, exit 0 | Ruff lint and format (26 Python files); Django 0 issues; no migration changes; ESLint/Prettier/TypeScript pass |
| `python scripts/dev.py smoke` | PASS, exit 0 | Five infrastructure checks plus signed S3 lifecycle and negative-auth checks |
| `python scripts/dev.py e2e` | PASS, exit 0 | **1 Chromium test in 3.7 s** against actual updated stack |
| `docker compose exec -T web npm run build` | PASS, exit 0 | 74 modules; 727 ms; JS 306.13 kB / gzip 96.68 kB |
| `python scripts/dev.py build` | PASS, exit 0 | All five container build targets; frontend 74 modules, 514 ms, same bundle sizes |
| `docker compose exec -T object-store nginx -t` | PASS, exit 0 | Proxy configuration syntax valid |
| `docker compose exec -T object-store-backend sh -n /opt/sii/storage-entrypoint.sh /opt/sii/storage-probe.sh` | PASS, exit 0 | Both shell files parse; `.gitattributes` enforces LF |
| Fresh-volume startup (procedure below) | PASS, exit 0 | Non-root image booted and authenticated health passed using a new named volume |
| Persistence across forced backend recreation (procedure below) | PASS, exit 0 | Synthetic object content retained, retrieved through proxy, then object/bucket deleted |
| `docker volume inspect sii-local_minio-data --format '{{.Name}}'` | PASS, exit 0 | Retired volume still exists; never mounted by new stack |
| `python scripts/dev.py secret-scan` | PASS, exit 0 | **83 source files, 300,681 bytes, 0 leaks**; includes shell/nginx files, excludes local credentials |
| Final `docker compose ps` / runtime inspection | PASS, exit 0 | All nine services running/healthy; only 5173/8000/8025 published on loopback; backend UID 10001 and credential config mode 0600 |

Seven new regression cases protect idempotent `.env` upgrade/secret preservation,
refusal to modify non-local configuration, four invalid credential inputs and
storage rejection of non-local mode. Existing default-deny API tests remain green.

Smoke now asserts PostgreSQL SELECT 1, RabbitMQ/worker ping, authenticated Redis,
SMTP NOOP, anonymous S3 403, eleven blocked internal/control ports and no backend
DNS entry from the API network. From the backend container, the S3 probe traverses
the proxy and verifies signed listing, anonymous and invalid-signature denial,
unique bucket creation, synthetic object PUT/GET equality, anonymous object denial,
and successful object/bucket DELETE. No business event or email is created.

## Additional storage procedures actually run

Fresh volume: `docker compose run -d --no-deps --name sii-storage-bootstrap-check
-v sii-local_storage-bootstrap-check:/data object-store-backend`; execute the
image's `storage-probe.sh health`, inspect running/healthy status, then stop and
remove only that temporary container. Its unused metadata volume remains. This
proves the corrected Dockerfile owns inherited metadata directories on first boot.

Persistence: create a random `sii-persistence-<UUID>` bucket and object with
curl SigV4 through `http://object-store:8333`; use credentials from container
environment via curl config stdin, never command arguments/output. Run
`docker compose up -d --force-recreate --no-deps --wait --wait-timeout 120
object-store-backend`, then GET and compare the exact synthetic payload and DELETE
only the newly created object/bucket. Bounded curl retries allow proxy DNS refresh.
No domain/customer data is involved. This verifies persistence, not backup/restore.

## Initial failures and corrections

- Initial SeaweedFS startup exited 255 because the upstream image's existing
  `filerldb2` directory was root-owned. Fixed recursive ownership in the build;
  corrected only that directory in the newly created development volume. Fresh
  volume startup was then tested successfully. No old MinIO volume was changed.
- The first network audit found the additional S3 gRPC listener on 18333. Added a
  separate internal storage network and S3-only nginx proxy, then extended smoke
  to reject that port and backend name resolution from the API container.
- First nginx startup exited 1 because its unused FastCGI temp directory targeted
  the read-only root filesystem. Explicitly moved all temp directories to tmpfs;
  configuration validation and startup then passed.
- An early test invocation ran during container recreation and returned “api is
  not running.” Reran after startup completed: 32 backend / 5 component tests pass.
- Ruff caught one 101-character line after the service rename; wrapped it and
  reran the full lint command successfully.
- The first manual persistence harness used PowerShell's CRLF pipe output, causing
  a `/dev/null` redirection error before any object write. Repeated with LF-safe
  `sh -c` arguments: persistence and cleanup passed.

## Limits and documentation review

Remote GitHub Actions remains unrun (no Git remote). Its existing `make smoke`
step executes the strengthened checks without a workflow change. Python/npm
audits and contract regeneration were not repeated: dependencies and API contracts
are unchanged, with their prior passing results in `SPRINT_01_VERIFICATION.md`.
No production, tenant-domain, multipart/large-object, restore, load, container CVE
or upstream transitive dependency scan is claimed. SEC-08 remains a later gate.

Master SHA-256 remains
`BE70C9C7B871001AE77D4941A5E06C4F5DD6261A2E8F501DEF0FC84C33B9AB6C`.
Reviewed purpose, side effects, fail-closed behavior and test documentation in all
changed Python/shell/config sources. Generated contracts/migrations/lockfiles were
not hand-edited. Updated ADR, dependencies, README, deployment/retention guidance,
security register, changelog, traceability and tracker. **STOP: Sprint 02 not started.**
