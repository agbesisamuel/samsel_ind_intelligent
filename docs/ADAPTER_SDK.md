# Read-only adapter SDK and pilot preparation

**BLOCKED: no authorised hardware/site.** No partner-approved physical profile,
customer agreement, installation or calibration evidence was supplied. The only
registered profile is `sii-simulator-v1`, a software fixture. It does not establish
compatibility with any named gateway, sensor, protocol or supplier. No configuration
flag or stored synthetic review can enable real go-live.

`sii.adapters.sdk.ReadOnlyAdapter` yields immutable `Sample` observations. The built-
in `SyntheticAdapter` performs no equipment/network I/O. Source timestamps require
explicit offsets and are converted to the same UTC instant without interpolation,
clock repair or unit conversion. Values must be finite, within the **fictional
simulator engineering range** and have at most four decimal places. These are not
customer food-safety limits. Stable event IDs bind gateway/sensor/source sequence.

`ReplayBuffer(path, gateway_id)` is an operator-owned private SQLite file on a
persistent local volume. FULL commits precede transmission. Reopen with the same
gateway/profile; changed source data under the same sequence is rejected. Pending
batches are bounded at 1,000 and retain original clocks/values. The transport must
verify TLS/device identity and a durable accepted/duplicate application receipt
before acknowledgement. MQTT PUBACK alone is rejected. No credentials are stored.
Known network/restart discontinuities are separate metadata and create no readings.
The current spool retains delivered history; monitor disk use and agree a reviewed
producer retention/export policy before a real adapter deployment. Disk/DB failures
propagate visibly rather than silently discarding pending data.

Never accept uploaded SQLite files or expose spool paths through APIs. This SDK
is an interface, not a sandbox for unreviewed plugins. A future partner adapter
requires source/licence/security review, actual read-only capability proof, original
clock/sequence/reset semantics, approved outbound network destinations and explicit
site/IT/customer authorization. No PLC/OT write interface is provided.

Run `python scripts/dev.py adapter-smoke`: three fictional source samples (including
zero) are buffered, a software disconnect is recorded, the file is closed/reopened,
and actual local TLS HTTPS delivery plus duplicate receipts empties the pending
batch. Existing `telemetry-smoke` additionally tests MQTT, malformed bodies,
foreign-topic denial, backfill and out-of-order source evidence.

`/integrations` shows exact-site counts, the permanent hardware/site blocker,
commissioning/route links and immutable synthetic daily/weekly review history.
Operational roles may append a review after recent MFA; auditors only read.
Snapshots preserve source-state categories (including delayed/unknown), outstanding
or exhausted processing, report queues/failures and unresolved response/delivery
counts with a server sampling time. Counts are diagnostics, not a go-live decision.
Server snapshots and PostgreSQL guards preserve original scope/actor/time. These
reviews are not physical acceptance, QA calibration or customer sign-off.

Generated migration `adapters/0001` belongs to Django; hand-authored `0002` adds
site ownership/immutable-evidence guards. Regenerate API/types with `dev.py contracts`.
Rollback code only after schema compatibility review; do not reverse evidence
guards or delete review/telemetry history as a cleanup technique.
