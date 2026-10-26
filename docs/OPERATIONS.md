# Local operation and support handover

Use DEPLOYMENT.md, RECOVERY.md, INCIDENT_RESPONSE.md, PRIVACY.md and DATA_RETENTION.md
together. This is a synthetic development stack, not an approved production service.
No human pager coverage, customer response time, cloud SLA or statutory retention
period is assumed. Named technical, QA, privacy and commercial owners must approve
those responsibilities before a real-site release.

## Upgrade and rollback

Preserve `.env`, independent encryption keys, local CA, database and private objects.
Run setup, up, migrate, seed-demo, test, lint, contracts, build and smoke with
`python scripts/dev.py`. Setup appends missing configuration and preserves secrets.
Never run a live API recreation concurrently with a pytest exec session. Generated
model migrations and OpenAPI/types belong to their generators; owned SQL migrations
document their guards. Sprint 12 adds billing/0001..0003 and support/0003..0004.
Runtime plan DML is explicitly revoked by prepare_local_database during migrate.

Revert application images only after a schema compatibility review and independently
verified backup. Never reverse scope/append-only guards, flush a database, remove
volumes or erase accepted telemetry/audit history as rollback. If an older image
cannot read the new schema, stop the affected local service and restore to a fresh
isolated target using RECOVERY.md; preserve the source for investigation.

## Outage and support

Check scoped freshness, latency, unresolved incidents, notification uncertain/dead
state and worker/report backlogs. Process health alone cannot prove monitoring.
Record incident owner, impact window and actual recovery evidence without secrets.
Preserve durable queues/outboxes and avoid uncertain duplicate notification sends.
Communicate through an approved human channel only after explicit authorization.
Customers must follow their own independently agreed site contingency procedure.

`/help` provides current diagnostics, onboarding steps, local ticket conversations,
release blockers and bounded acceptance/report references. Owners/site administrators,
QA/operations and auditors see their granted-site queue; operators see only their
own requests. Auditors cannot post. Platform flags and temporary support diagnostics
grants do not reveal ticket content. Tickets remain inside the customer workspace;
creating one does not email SAMSEL, assign an on-call employee or start an SLA clock.
Recent-MFA owner approval can grant an independent active support staff member only
expiring site diagnostic counts, never measurements, files or membership authority.

Original ticket text and events are immutable. Replies use a revision check and
append evidence; changing support status never closes a safety incident. Use plain
fictional text locally and exclude credentials, unrelated personal data and payment
details. Admission is limited to 20 unresolved requests per user/site. Lost creation
responses can replay the same request UUID/content without a duplicate original.

## Privacy, export and termination

Verify requester identity and controller authority, record request/scope/deadline/
reviewer, assess legal hold and other individuals' rights, produce scoped exports,
and deliver through a reviewed secure channel with receipt. Reports/activity exports
alone are not a complete data-subject response. Include billing contacts/drafts and
support narratives in the data map; ticket audience and evidence retention matter.
Do not paste a complete request or credentials into general logs or public tickets.

Before termination, agree export completeness, ongoing site contingency and retention
with the owner/QA/controller. Revoke authorized sessions/devices/new access only at
the agreed handover; an expired subscription does not do this automatically. Preserve
immutable source/evidence under reviewed retention/hold, including encrypted backups.
There is no implemented bulk purge, automated backup expiry or tenant key-destruction
shortcut. Record those limits honestly; production deletion tooling/policy needs a
separate reviewed scope. No legal deadline or accounting retention rule is invented.

## Recovery and cost review

Run security-check and restore-drill; keep independent keys and immutable checkpoint
evidence. Review real RTO/RPO against a future agreed target. Local restore does not
prove scheduled cloud backup custody, PITR, region recovery or pager response.
Record actual infrastructure, storage/egress, support hours, commissioning/calibration,
provider charges, insurance and retention cost per authorized site before prices or
SLAs are approved. The synthetic reference-load rig does not establish cost-to-serve.
