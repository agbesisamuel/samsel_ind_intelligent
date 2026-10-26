# Data retention boundary

Sprint 01 originally had no domain records. Subsequent local sprints retain synthetic
telemetry, immutable rule/incident evidence, contact consent, notification intents,
attempts and delivery issues. No real customer fixtures are authorized.
Sprint 08 adds encrypted text attachments and immutable actor/narrative chronology.
No automatic deletion or key rotation is enabled. Preserve the separate evidence
key with approved backup procedures; key loss makes stored evidence unrecoverable.
Local PostgreSQL, queue, Redis and SeaweedFS volumes persist until explicitly removed
by their owner. `down` does not remove volumes; no automatic deletion job exists.
The retired `sii-local_minio-data` volume is retained separately and is not mounted
by the current stack. Storage smoke removes only its own uniquely named synthetic
object and bucket; it never sweeps customer or unknown data.
Future retention classes, export-before-deletion, legal hold and backup expiry
need customer/legal review. Master draft durations are proposals, not statutory rules.

Sprint 02 adds synthetic identities, scope records and append-only audit. Invitations
expire after 48 hours, resets after 30 minutes, pending MFA after 10 minutes and
sessions after 8 hours. Expiration denies use; it does not automatically erase
identity/audit records. Throttle cleanup removes only bounded expired counters.
No retention/legal-hold policy is inferred from these security lifetimes. Reset-demo
preserves identities and evidence, and never flushes the database.

Sprint 03 calibration, placement, site-pack, test and QA acceptance records are
append-only. Record amendments as new versions; archived inventory and retired
devices preserve original references. No retention purge or legal-hold exception
is implemented. Synthetic QA snapshots do not constitute physical calibration or
real customer acceptance.

## Sprint 04 telemetry

Synthetic measurements, rejection hashes, outbox lifecycle and SQLite producer
spools persist locally. Measurements/rejections are append-only; no retention purge
job is enabled. Quarantine stores metadata, not arbitrary bodies. Broker dead letters
are private and may contain rejected protocol bodies; restrict investigation and
retain only through a documented incident review. Establish production retention,
quotas and deletion/export policy before customer ingestion. Do not delete accepted
history to retry a worker. Revoked credential metadata remains auditable; production
secret destruction/backup retention must be reviewed together.

## Sprint 05 evidence

Freshness policy approvals and transitions are append-only. Current projections
are rebuildable and are not a substitute for raw readings or transition history.
Manual CSV imports retain manual provenance; preview adds only an audited preview
action. No automatic retention purge is enabled. Preserve rule/incident/report
references when a later reviewed retention workflow is implemented.

Sprint 09 reports are encrypted derived artifacts with 24-hour access expiry;
immutable request/snapshot/audit metadata and expired local ciphertext are retained
for reviewed cleanup. No automatic source/audit deletion. Download handles last at
most five minutes and require the original user plus current exact-site authority.
See REPORTS.md; production retention, backups and legal holds need reviewed policy.

Sprint 12 retains subscription origins/term history, manual finance drafts and
support originals/events. Contacts/current support state can change; source evidence
is append-only. No automatic expiry deletes records and no commercial term erases
telemetry. No statutory/accounting duration is asserted. See OPERATIONS.md for
reviewed export, termination and hold responsibilities.
