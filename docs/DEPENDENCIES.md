# Dependency and licence inventory — ADR-001 evidence

Resolved on 2026-10-20/21 from official package registries. Production approval is
not implied. Full Python versions/hashes are in `apps/api/requirements.lock`;
full npm versions/integrity hashes are in `apps/web/package-lock.json`.
Compose and Dockerfiles pin upstream images by release tag **and SHA-256 digest**.
Do not use floating `latest` tags when updating these references.

## Runtimes and infrastructure

| Component | Selected version | Licence / support decision |
|---|---|---|
| Python | 3.13.12 | PSF; supported 3.13 line; Debian slim development image |
| Node | 24.22.0 container; host check also 24.16.0 | MIT; 24 LTS |
| PostgreSQL | 17.11 | PostgreSQL licence; supported major through November 2029 |
| RabbitMQ | 4.3.6 management | MPL-2.0; community support through January 2027; recheck before then |
| Redis server | 8.2.10 | AGPLv3 / RSALv2 / SSPLv1 choices; no permissive-licence assumption, legal review before distribution |
| SeaweedFS | 4.48, source revision 530be3e37 | Apache-2.0; current stable community-maintained release; ADR-006 replaces MinIO |
| nginx S3 proxy | 1.30.6-alpine | BSD-2-Clause; current stable release, isolates backend control listeners |
| Base OS | Debian Bookworm slim, pinned digest | Mixed distribution licences; security patch refresh required |
| Mailpit | 1.31.6 | MIT; local capture only, no relay |
| Gitleaks | 8.30.0 | MIT; pinned official GHCR digest, source-only offline scan |

SeaweedFS 4.48 was verified on 2026-10-21 as the current stable release (published
2026-09-28), with an active upstream repository. Registry manifest digest:
`sha256:4e61d15fd35994cb1e43e1e553dff106794841fd9a99ade2fc8c8bfce4d7872d`.
Its upstream image includes Alpine 3.24.2 and curl 8.22.0; the local wrapper adds no packages.
The nginx image is pinned to
`sha256:970364228b1e4f932abc22d321932816782cca8a20b85a77552a7cfe9acfb3b5`.
The application continues to use Debian images. Record the image digest on refresh,
since an active release stream does not guarantee future maintenance or an SLA.
MinIO and its source-build Go stage have been removed from active dependencies.
The obsolete local image/volume may remain on a developer machine for recovery;
neither is used by Compose. No unsupported-dependency exception is accepted.

## Application and test tooling

| Component | Exact version | Licence |
|---|---|---|
| Django | 5.2.18 | BSD-3-Clause; LTS security support through April 2028 |
| Django REST Framework | 3.18.3 | BSD-3-Clause |
| drf-spectacular | 0.30.0 | BSD-3-Clause |
| psycopg / binary | 3.3.6 | LGPL-3.0-or-later; binary distribution includes bundled library obligations |
| Celery | 5.6.3 | BSD-3-Clause |
| redis Python client | 7.4.1 | MIT |
| Gunicorn | 24.1.1 | MIT |
| boto3 / botocore | 1.43.116 / 1.43.116 | Apache-2.0; official AWS S3 SDK, local endpoint only |
| jmespath / s3transfer | 1.1.0 / 0.19.3 | MIT / Apache-2.0; SDK transitive dependencies |
| Pytest / pytest-django | 9.1.1 / 4.14.0 | MIT / BSD-3-Clause |
| Ruff | 0.17.1 | MIT |
| pip-tools / pip-audit | 7.6.2 / 2.10.1 | BSD-3-Clause / Apache-2.0 |
| React / React DOM | 19.3.1 | MIT |
| React Router DOM | 7.18.4 | MIT |
| TanStack Query | 5.104.5 | MIT |
| openapi-fetch / openapi-typescript | 0.15.2 / 7.13.0 | MIT |
| TypeScript | 5.9.3 | Apache-2.0 |
| Vite / React plugin | 8.3.4 / 6.1.2 | MIT |
| Vitest / jsdom | 5.0.5 / 27.4.0 | MIT |
| Testing Library React / user-event / jest-dom | 16.3.3 / 14.6.8 / 6.9.1 | MIT |
| Playwright | 1.64.1 | Apache-2.0 |
| ESLint / typescript-eslint | 10.13.0 / 8.72.0 | MIT |
| Prettier | 3.9.10 | MIT |

Release streams with no formal LTS policy are locked to verified stable registry
releases, not described as having a contractual support SLA. Licence inventory is
engineering groundwork, not a legal conclusion about proprietary distribution.
Application code remains proprietary; no white-label IoT core is used. No chart,
form or component-system dependencies are added before actual UI workflows need them;
the shell uses accessible native HTML controls.

## Refresh workflow

1. Check official support/release pages and security advisories. Keep Django on supported LTS.
2. In a Python 3.13 environment install pip-tools 7.6.2, then from root run
   `pip-compile --extra dev --allow-unsafe --generate-hashes --output-file apps/api/requirements.lock apps/api/pyproject.toml`.
   `--allow-unsafe` locks build-tool dependencies (pip/setuptools); it does not disable hash verification.
3. Review package updates with npm, commit both manifest and package-lock, use `npm ci` in builds.
4. Resolve image release tags to registry digests, review licences and update Dockerfiles/Compose.
5. Regenerate contracts; run up/migrate/test/lint/build/smoke/e2e/audit/secret-scan.
6. Record findings and dated results in status/security register. Do not suppress advisory failures silently.

## Verification sources

Sprint 08 added only the four S3 SDK entries above; existing pins were preserved.
Verified the [official Boto3 1.43.116 API documentation](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/put_object.html)
and installed package licence metadata. Python/npm audits returned zero known
findings on 2026-10-21. Lock generation used a writable temporary copy of the existing
lock with pip-compile, then copied the generated result back; no manual hash edits.

- [Django support table](https://www.djangoproject.com/download/) and [PyPI Django releases](https://pypi.org/project/Django/).
- [Python support lifecycle](https://devguide.python.org/versions/) and [Node releases](https://nodejs.org/en/about/previous-releases).
- [PostgreSQL support](https://www.postgresql.org/support/versioning/) and [RabbitMQ releases](https://www.rabbitmq.com/release-information).
- [Redis releases](https://github.com/redis/redis/releases) and [Redis licensing](https://redis.io/legal/licenses/).
- [SeaweedFS stable release](https://github.com/seaweedfs/seaweedfs/releases/tag/4.48), [Apache-2.0 licence](https://github.com/seaweedfs/seaweedfs/blob/4.48/LICENSE), and [S3 authentication](https://github.com/seaweedfs/seaweedfs/wiki/S3-Credentials).
- [nginx stable release](https://nginx.org/en/download.html) and [licence](https://nginx.org/LICENSE).
- [MinIO archive](https://github.com/minio/minio): historical replacement rationale, ADR-006.
- [Mailpit releases](https://github.com/axllent/mailpit/releases), [ESLint support](https://eslint.org/version-support/), and package metadata in the lock files.

## Sprint 02 additions (2026-10-21)

| Component | Locked version | Licence / purpose |
|---|---|---|
| PyOTP | 2.10.0 | MIT; TOTP with replay protection implemented by the application |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause; authenticated encryption of TOTP seeds |
| cffi | 2.1.1 | MIT-0; cryptography transitive dependency |
| pycparser | 3.11 | BSD-3-Clause; cffi transitive dependency |

Verified from official registry metadata and the installed distribution metadata.
The [current stable cryptography release](https://pypi.org/project/cryptography/)
and [release notes](https://cryptography.io/en/stable/changelog/) supersede the
initial 49.0.0 selection rejected by PYSEC-2026-3552. No advisory is ignored.
All other existing exact pins are preserved. The full hash lock includes transitive
packages; `audit` checks every pinned entry directly with `--no-deps --disable-pip`,
avoiding redundant temporary installation. This does not skip transitive entries.

## Sprint 04 addition (2026-10-21)

Paho MQTT **2.1.0**, EPL-2.0 OR BSD-3-Clause, is the hash-locked simulator client.
The existing RabbitMQ **4.3.6** bundled MQTT plugin supplies the broker; no additional
broker image is introduced. Python's SQLite library supplies the persistent local
simulator spool. Existing cryptography **50.0.2** supplies device-secret encryption
and local TLS certificates; existing Gunicorn **24.1.1** serves device HTTPS.
Sources: [Paho release](https://pypi.org/project/paho-mqtt/2.1.0/),
[Paho client documentation](https://eclipse.dev/paho/files/paho.mqtt.python/html/),
[RabbitMQ MQTT](https://www.rabbitmq.com/docs/mqtt),
[RabbitMQ access control](https://www.rabbitmq.com/docs/access-control).
Paho's volatile client session is not used as durable storage. Callback API v2 is used.

## Sprint 09 additions (2026-10-21)

ReportLab **5.0.1** (BSD-3-Clause), Pillow **13.0.0** (MIT-CMU), with existing
charset-normalizer **3.5.2** (MIT). Exact pins and hashes regenerated with pip-compile
from the existing lock; no unrelated dependency updates. ReportLab uses escaped text
and built-in fonts only; image/remote-resource decoding is not exposed.
Sources: [ReportLab release](https://pypi.org/project/reportlab/5.0.1/),
[Pillow release](https://pypi.org/project/Pillow/13.0.0/). Full Python/npm audits passed.

## Sprint 10 tooling and OS patch baseline

No new application package was added. Trivy **0.76.0** is digest pinned in scan
evidence; CycloneDX inventories are generated with existing pip-audit/npm tooling.
The 82 installed Python distributions each expose licence metadata; node SBOMs
include declared package licences. This inventory does not replace legal review of
transitive, native, bundled and copyleft components (including storage/broker tools).

Both Debian development images explicitly pin security packages in their Dockerfiles
to the registry versions verified on 2026-10-21. Refresh pins together with a rebuilt
SBOM, scan and tests when repository versions change. This development baseline was
verified on linux/amd64; the libcap2 binary revision is architecture specific.
CONTAINER_SECURITY.md records residual OS and pip-vendored findings that the
application dependency audits do not cover. None is silently ignored.
