# Privacy groundwork

Sprint 02 stores local synthetic identities (email, password hash, verification,
encrypted MFA seed, hashed recovery proofs), memberships/roles/sites and audit
identifiers/evidence hashes. No customer data is authorized. Invitations and reset
links remain in the local Mailpit sink; that UI is loopback-only and has no relay.
Only language preference is stored in browser localStorage; sessions use HttpOnly
cookies. No analytics, remote fonts or tracking scripts are used. Logs and public
errors do not include passwords, MFA seeds, bearer links or full email bodies.

Controller/processor roles, DPA, subprocessor register, DPIA screening, data subject
workflows and legal review remain incomplete. No GDPR/compliance certification
claim is made. Privacy deletion must preserve legal/audit obligations through a
reviewed policy; no blanket customer deletion command exists.

Sprint 03 qualification references may contain responsible-person/technician names
and document references. Keep them fictional locally. Sprint 08 permits bounded
encrypted UTF-8 text attachments, actor-email snapshots and audited downloads; no
external URL fetch exists. Exact site permissions restrict these records;
SQL append-only guards retain history until a reviewed retention policy is built.

## Device telemetry boundary

Gateway identifiers, times, engineering values and source provenance are customer
operational data. Current fixtures are fictional. Device secrets are encrypted with
a separate environment key, never returned after issue and never stored in browser
URLs or simulator spools. Rejected input retains only a digest/size/reason, avoiding
arbitrary payload disclosure. The private broker dead-letter queue requires controlled
investigation. Real data collection remains subject to customer/site authorization.

## Sprint 10 classification and request handling

Identity/contact data is personal; telemetry, incident narratives and qualification
references are confidential operational data and can contain personal information.
Authentication/device/encryption material is secret. Report/download handles are
sensitive capabilities and must not enter logs. Support diagnostic aggregates remain
confidential and require an expiring owner-approved exact-site session.

An authenticated owner may request a scoped operational export through the report
and incident activity interfaces. A complete data-subject request also requires
identity verification, controller review, related account/audit records and secure
delivery; the report button alone does not complete that legal workflow. Record the
request, scope, reviewer, lawful basis, deadlines and delivery receipt outside any
free-text field containing secrets.

Deletion/termination requires a reviewed retention schedule and legal-hold check.
Revoke sessions/credentials and new access first; preserve immutable incident/audit
evidence and backups for approved retention. No bulk erasure endpoint bypasses these
guards. Key destruction is not an automatic substitute for reviewed deletion because
keys and backups span retained evidence. Production DPA, subprocessor/country review,
data-subject deadlines and approved purge/key lifecycle remain human release gates.

Sprint 12 includes billing contacts/references, immutable nominal finance drafts/
term history and internal support narratives/actors. Owners see tenant billing;
site-only operators do not. Operators see own tickets; authorized reviewers see
the granted-site queue. No supplier dispatch, card data or payment provider exists.
Include these in reviewed access/export/retention requests (OPERATIONS.md). Immutable
evidence cannot be silently rewritten as a privacy shortcut. Controller/legal-hold
review and separately authorized purge design remain gates before customer data.
