# Container scan evidence and residual release gates

2026-10-21: Trivy **0.76.0**, digest
`sha256:2416d1f74045b57274df1a340eee6b510cacd73c66a6ccb8da092b117eb7d222`,
scanned an exported local API image without Docker socket access. Advisory cache,
image archives and full JSON results are retained in ignored `.artifacts/security/`.
The scanner's exit zero means the scan ran; it does not mean zero vulnerabilities.
Python lock and npm audits are separate checks and cannot substitute for image scans.

The first image had 9 critical/87 high package findings. Available Debian security
updates were applied with explicit pins in both development Dockerfiles: libcap2,
GnuTLS, PCRE2, OpenSSL and perl-base. The obsolete unused ensurepip bootstrap wheel
was removed; virtual environments inside this image require `--without-pip` and the
installed tooling. Do not manually patch generated/vendored package code.

The second API scan reports **2 critical, 65 high, 119 medium, 98 low, 6 unknown**
package findings. Several packages share one source-level CVE. These are retained,
with no blanket ignore file. Findings below require production security review;
this development image is not a production release image.

| Finding group | Current assessment and required action |
|---|---|
| CVE-2023-45853, zlib | Debian says vulnerable MiniZip code is not built into the Bookworm zlib binary. Verify binary composition in the final release image. |
| util-linux mount/nsenter/partition CVEs | API runs non-root with no-new-privileges and no SYS_ADMIN; application exposes none of these commands or device images. Remove unneeded tools in a dedicated production image and review capabilities. |
| gzip LZH, ncurses infocmp, Perl Archive::Tar | No application path invokes these tools on submitted data. Development tooling remains present; remove from production runtime. |
| SQLite FTS5 | Used only by the fixed local simulator spool; application DB is PostgreSQL. No uploaded SQLite files or FTS queries. Production adapter package needs its own scan. |
| OpenSSL DTLS CVE-2026-84782 | Shipped OpenSSL 3.0.22 still affected upstream; system uses TCP TLS, no DTLS surface. A production image must adopt a supported fixed library and repeat TLS tests. |
| systemd-homed | No systemd daemon or home management runs in this container. Review final runtime package removal. |
| pip vendored msgpack 1.1.2/urllib3 2.7.0/setuptools metadata 70.3.0 | Installed standalone packages are current (1.2.3/2.8.0/84.2.1), but supported pip 26.2.2 still carries older vendor components. Do not dismiss these as absent solely from importlib.metadata. Pip is build/development tooling, never a request handler; use a separate production runtime without package-install tooling. |

Medium/low available Debian updates also remain in the full scan. Review all
transitive binary/tooling components, not only application imports. Scan web,
storage, database, broker, cache and mail images as part of the final production
image selection. No claim of full-fleet zero findings is made.

Primary evidence:
[Debian MiniZip scope](https://security-tracker.debian.org/tracker/CVE-2023-45853),
[Debian infocmp assessment](https://security-tracker.debian.org/tracker/CVE-2025-69720),
[Debian DTLS status](https://security-tracker.debian.org/tracker/CVE-2026-84782),
[Trivy Python metadata coverage](https://www.trivy.dev/docs/latest/guide/coverage/language/python/).
Reachability assessments above are local engineering inferences, not vendor VEX
or external penetration-test sign-off. **Production security gate remains open.**

## Completed eight-image inventory

Full reports and exact image identities are in `.artifacts/container-audit/`.
API/web package scans preceded final non-root/ownership changes; application locks,
base OS and bundled package versions are unchanged by those changes. Final runtime
privilege checks and frontend tests/build/browser checks were repeated afterwards.

| Image family | Critical | High | Medium | Low | Unknown |
|---|---:|---:|---:|---:|---:|
| API | 2 | 65 | 119 | 98 | 6 |
| Web tooling | 1 | 62 | 102 | 88 | 1 |
| SeaweedFS backend | 0 | 4 | 15 | 1 | 1 |
| nginx proxy | 0 | 2 | 6 | 0 | 0 |
| PostgreSQL | 4 | 95 | 195 | 173 | 5 |
| RabbitMQ | 0 | 0 | 21 | 4 | 0 |
| Redis | 1 | 57 | 91 | 85 | 1 |
| Mailpit | 0 | 0 | 0 | 0 | 1 |

Additional review findings:

- npm's bundled brace-expansion 5.0.9 and undici 6.28.0 are separate from the
  zero-finding application lock. The official npm 12.2.0 archive was inspected and
  still bundles the same versions; upgrading to it would not fix these findings.
  Preserve upstream package ownership; do not hand-edit vendor directories. Package
  managers belong in isolated build/development tooling, not production serving.
- SeaweedFS's Go 1.26.8/x/net 0.58.0 findings concern HTTP/2 settings, crafted Range
  parsing and TLS ECH. The current isolated backend receives HTTP/1.1 via nginx,
  uses plain HTTP on the private storage network, and the application constructs
  all S3 headers/keys and sends no Range headers. No S3 endpoint is published or
  exposed through browser routes. These local reachability restrictions must not
  be assumed for a future public object-store deployment. Upstream rebuilt binaries
  and an independent review remain required before production.
- nginx's libexpat/libx11 findings concern optional XML/X11 functionality. The fixed
  proxy configuration loads no such dynamic processing modules and performs only
  byte forwarding. Adopt a minimal patched production image and re-scan.
- PostgreSQL/Redis findings include inherited OS tooling and SQLite/XML libraries;
  PostgreSQL also includes Go-built privilege-drop tooling. These services have no
  published ports. Application queries are parameterized and expose neither XML
  SQL evaluation nor arbitrary SQLite files. These are reachability observations,
  not blanket acceptance of all inherited findings or proof against SQL injection.

Sources: [official npm 12.2.0](https://github.com/npm/cli/releases/tag/v12.2.0),
[Go TLS ECH](https://pkg.go.dev/vuln/GO-2026-6607),
[Go Range parsing](https://pkg.go.dev/vuln/GO-2026-6609),
[Go HTTP/2](https://pkg.go.dev/vuln/GO-2026-6611),
[Alpine libexpat](https://security.alpinelinux.org/vuln/CVE-2026-77214).
This inventory is a release-blocking remediation register, not a clean production
scan. No ignore file or false passing severity gate was introduced.
