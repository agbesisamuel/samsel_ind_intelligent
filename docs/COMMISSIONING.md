# Commissioning and activation gates — Sprint 03

The local inventory supports site → building → zone → sensor/gateway scope. Every
record has immutable organisation/site anchors; PostgreSQL composite foreign keys
also protect bulk/raw writes. Device zone/gateway/source identifiers cannot be
reassigned through ordinary CRUD. Use retirement/archiving to preserve references;
there is no hard-delete endpoint or silent transfer.

Devices start planned, can enter commissioning, become degraded, and retire
permanently. Active transitions require the monitoring activation gate. Sites
remain planned in this local environment. Calibration status is calculated at
read time: unknown, expired, synthetic_valid (local), or valid (future qualified
source). None of these asserts food safety. Missing data is never a valid reading.

Use the Inventory & commissioning screen to register buildings, rooms, gateways
and sensors, record calibration references (explicit QA role only), record sensor
technician/placement/read-only scope, create a site responsibility/contingency pack,
and append feed/breach/no-data/route test evidence. In this environment every
such entry is explicitly **synthetic**. These are manually recorded test references,
not proof that an unimplemented sensor feed or customer alert was delivered.

Owner/site administrators configure inventory with fresh step-up. QA approval
requires an explicit site QA assignment, verified MFA and step-up; owner/platform
flags do not imply QA. A pack requires current sensor calibration/placement,
non-retired commissioning devices, all four passing drill references, read-only
scope, customer reference and contingency reference. An accepted synthetic pack
stores the exact normalized snapshot and hash. Later configuration/test/calibration
changes or expiry make its `current` flag false without changing its original
snapshot. Amend evidence by adding a new version, not editing the old row.

**No local pack can activate real monitoring.** GET activation lists blockers;
POST activation returns 409 and audits the attempt. Required verified rule versions
(Sprint 06), notification routes (Sprint 07), real customer/QA acceptance and a
separately authorized live environment remain unmet. Submitted flags cannot turn
synthetic evidence into physical qualification or enable a bypass.

Before any live pilot, independently verify qualified placement/calibration,
read-only network approval, customer-specific SOP/limits/cadence, breach/no-data
and notification drills, recipient consent, independent contingency procedure,
training, support terms and signed customer acceptance (master section 15).
Real site access remains **BLOCKED: CUSTOMER/SUPPLIER APPROVAL REQUIRED**.
