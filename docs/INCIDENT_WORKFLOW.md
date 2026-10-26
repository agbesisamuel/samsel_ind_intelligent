# Human incident response

Sprint 08 is a synthetic workflow, not customer food disposition or automated control.
At `/incidents`, filter the exact permitted site's episodes and inspect chronological
events, provider attempts, attachments and observed recovery independently.

Responders (owner, site admin, QA, operations, operator) can acknowledge, investigate,
record corrective action and append amendments. Auditors read but cannot mutate.
Assignment requires owner/site admin/QA/operations; the assignee must have a current
response grant to the same site. Both service and database guard new assignments.
Old assignments remain historical after role revocation; they do not grant access.

The normal lifecycle is open → acknowledged → investigating → awaiting QA → QA
reviewed → closed. QA review/close require an explicit site QA role and recent MFA;
ownership alone is insufficient. Close additionally requires observed recovery and
a written reason/reference. Recovery alone never closes. Evidence/action changes
invalidate existing review; a new breach resets response to open and preserves all
previous review/acknowledgement history. Closed records accept explicit amendments,
not silent edits. Human action never declares food safe or sends an OT command.

Commands include current revision and replay UUID. Shared gateway-first locking
serializes human actions with automatic observations. Stale revisions fail; exact
replay returns without appending duplicates; conflicting reuse fails. Actor email
is snapshotted with immutable actor ID/time and text for human reconstruction.
All timeline and attachment metadata is append-only in PostgreSQL. Database owner
bypass remains a separately documented hardening concern.

## External evidence

Only `.txt`, `text/plain`, valid UTF-8, 1..65536 bytes is accepted. Multipart request
bytes are capped at 128 KiB before temporary-file parsing. Controls, active markup,
invalid encoding and malware-test content are rejected. Images/PDF/office/archive
uploads are disabled until a tested scanning/re-encoding pipeline exists; no scanner
is falsely claimed. No URL fetch/import path exists, preventing evidence-upload SSRF.

The maintained AWS S3 SDK signs requests to the fixed private SeaweedFS proxy.
Fernet authenticated encryption uses a separate generated EVIDENCE_ENCRYPTION_KEY.
The encrypted envelope binds org/site/artifact path and SHA-256 checksum. Only
ciphertext reaches S3; swapped/corrupt content fails closed. UUID paths are server
owned; filenames cannot choose keys. Authenticated downloads recheck incident/site,
verify/decrypt content, audit access, force `.txt` attachment and no-store/nosniff/
sandbox headers. No public object links or reusable bearer URLs are issued.

Upload and event metadata commit together; a failed metadata transaction attempts
deletion of only its newly created object. Failed cleanup appends an orphan marker
for investigation. Encryption key backup/rotation is mandatory before any future
production deployment; losing it loses evidence. Keep the key outside source/logs.

## Export and operations

Managers, QA, operations and auditors may export bounded JSON activity (at most
10,000 events); operators cannot export. The export includes scope, provenance,
incident state, immutable timeline and attachment metadata, and audits access.
Provider evidence remains separately inspectable. Support approval is a Sprint 10
workflow and grants no implicit access here. Reports are Sprint 09.

New APIs under the incident prefix: commands, assignees, attachments, per-attachment
download, notifications and activity. Normal list/detail/events remain scoped.
`python scripts/dev.py evidence-smoke` verifies real encrypted storage round-trip,
plaintext absence and checksum denial, then deletes only its unique test object.
Generated incidents/0003 adds response fields/attachments; /0004 and /0005 are
documented SQL identity/scope/immutability/assignment guards. Preserve source records
and volumes on rollback; do not reverse against populated customer data.
