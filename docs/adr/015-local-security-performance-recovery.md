# ADR-015 — Local hardening proof and explicit production gates

Accepted for local synthetic development, 2026-10-21.

Separate migration ownership from the non-owner runtime SQL identity. Application
processes run non-root with no capabilities; the web toolchain generates contracts
in container scratch before the host copies generated artifacts. Keep development
secret sharing explicit; production requires per-service custody and settings.

Support is an owner-approved, expiring, revocable diagnostics capability with every
access logged. It grants no ordinary membership or raw-data/file access. Audits are
append-only/hash verified and restored against an earlier encrypted checkpoint;
external immutable checkpoint custody remains a production requirement.

Telemetry publishing and consumption are independent. A measured four-shard
deployment had unstable P95 under uneven gateway assignment. Sixteen fixed queues,
four supervised groups and a separate publisher met the 20×40×1/min local baseline.
Each gateway is serial; retries remain source-idempotent. A shard modulus change
requires draining old queues first. No automatic elastic queue resizing is provided.

Use an independent encryption key for the bounded database/object backup bundle.
Verify actual restore/decryption in disposable containers on an unexposed internal
network, preserve source volumes, record measured timing and retain failure evidence.
On-demand local recovery is not scheduled production RPO or cloud uptime proof.

Scan entire images as well as application locks. Retain full findings and declared
licences; do not suppress severity without component/reachability evidence. Current
OS/vendor tooling findings and external review remain production release gates.
Passing local CI cannot enable production, real telemetry or customer go-live.
