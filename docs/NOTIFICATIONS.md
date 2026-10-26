# Synthetic notification delivery

Sprint 07 uses Mailpit capture only, with no relay or paid SMS. Every message starts
with TEST and states synthetic provenance. NOTIFICATION_PROVIDER defaults to
local_capture; unsupported adapters fail closed. Production provider secret wiring,
idempotency and deployment require separate approval.

Managers with recent MFA select an existing verified account with an exact site
grant. A 30-minute hashed proof is emailed to capture; only that signed-in account
can confirm. Consent is single-use/revocable and checked with current grants before
every attempt. In-flight SMTP cannot be recalled. Staff status cannot manufacture
another user's opt-in. Routes explicitly select classifications, severity, verified
primary/contingency contacts, IANA timezone and local shift minutes. 0..1440 means
all day; overnight shifts and both DST-fold occurrences work. Separate routes
support multiple recipients. Optional escalation requires a verified secondary
and 30..86400-second delay. Content is immutable; enabled is an audited switch.

New routes never retroactively send old events. A missing match creates a visible
delivery-support issue. TEST drills create notification intent without industrial
incidents. An independent five-second worker consumes persisted opened/recurred
events. Event-plan ledger and all intents commit atomically; deduplication prevents
restart floods. Versioned envelopes are checked against persisted source/scope.
Composite FKs and immutable anchors guard raw writes.

Known failures retry after 30/60/120/240 seconds, with five total attempts before
dead state. Outcomes are append-only with safe error codes. Failures create support
issues and one configured contingency intent; contingency cannot recurse. Accepted
retry resolves that intent's issue. No-route issues remain visible: adding a route
does not pretend the missed alert was delivered.

Acceptance is not mailbox delivery, reading or human acknowledgement. Unacknowledged
incidents still escalate; human acknowledged status cancels escalation (workflow in
Sprint 08). Recovery alone leaves work open. Maintenance defers until explicit
expiry, then rechecks consent, scope, acknowledgement and overlapping windows.

SMTP cannot ensure exactly-once behavior if a worker dies between send and commit.
A lost 60-second lease or ambiguous disconnect becomes uncertain and is never
automatically resent. Investigate capture/provider evidence before an explicit new
TEST drill. Dead/uncertain history stays visible; no production exactly-once claim.

`/notifications` exposes consent, route creation/test, attempts and health in
English/Danish. An absent 90-second worker heartbeat is unknown/delayed, never healthy.
Queue/dead/issue counts are site scoped. API paths: alert-candidates, alert-contacts
(confirm/disable), alert-routes (enabled/test), notifications and notification-health
under the org/site prefix. No staff bypass/public customer metrics were added.

Run `python scripts/dev.py notification-smoke` or its Make alias for real local proof
and capture. Only reserved synthetic identities are used; proof stays out of logs,
the drill route is disabled afterward and evidence retained. CI uses the same drill.
Notifications/0001 is generated, /0002 documents SQL guards, /0003 permits clearing
consumed hashes. Preserve volumes on rollback. No new dependencies. Customer sends,
production providers, telecom costs and real site acceptance remain blocked.
