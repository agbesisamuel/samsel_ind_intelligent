# Foundation incident runbook

For the implemented synthetic human-response application, see INCIDENT_WORKFLOW.md.
For delivery support issues and uncertain SMTP attempts, see NOTIFICATIONS.md.

This is local development, with no customers monitored and no on-call SLA.
If a service fails, inspect `docker compose ps` and the affected logs, restore
configuration or restart only this stack, then run `make smoke` and `make test`.
Do not infer site safety from green process health or lack of alerts.

If a secret is committed, stop sharing it, rotate affected credentials and review
history/access. Do not upload raw `.env`, resolved Compose configuration, customer
payloads or authentication logs to issue trackers. Production containment,
notification responsibilities and contractual escalation are future release gates.
Customers must retain independent monitoring and response procedures.

## Sprint 10 operations

Check scoped ingestion metrics and rule lag alongside broker queue depth, freshness
watcher age, notification pending/retry/uncertain/dead state, report failed/expired
leases, database capacity and encrypted-backup checkpoint age. A healthy process
does not imply timely rules or alert delivery. Restrict global broker/DB diagnostics
to infrastructure operators; approved support sessions expose only scoped aggregates.

Telemetry has one confirmed publisher plus 16 serial gateway-shard consumers in
four supervised services. Drain existing queues before any shard-modulus change.
Restart
individual processes without deleting queues/outboxes. Five exhausted attempts are
visible as dead records. For investigated synthetic records only, bounded replay is
`telemetry_worker replay --confirm-local --limit 50`; domain receipts use
`domain_worker --replay-local --limit 50`. Both audit replay and preserve source
identity; neither command accepts a customer endpoint or erases evidence.

Uncertain notification transport outcomes require human investigation; automatic
resend could duplicate a message. Lost report leases become explicit failed jobs;
retry is bounded and reuses immutable snapshots. Restore only into the isolated
target described in RECOVERY.md. Preserve ciphertext, checkpoints and audit history.
Production cloud pager delivery and on-call drills require separately approved
provider/customer configuration; local Mailpit cannot prove cloud alert coverage.
