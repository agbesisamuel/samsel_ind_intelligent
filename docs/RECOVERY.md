# Local encrypted recovery drill

Run `python scripts/dev.py restore-drill` after a healthy local stack. It captures
an audit checkpoint, a custom-format PostgreSQL dump and private encrypted objects,
then encrypts the complete bounded bundle with the independent
`BACKUP_ENCRYPTION_KEY`. Back up both that key and `EVIDENCE_ENCRYPTION_KEY` through
separate approved custody; neither is embedded in the bundle. MFA/device keys also
remain separate configuration. Losing keys prevents recovery by design.

The command creates uniquely named temporary PostgreSQL and S3 containers on an
internal network with no published ports, restores into `sii_restore`, verifies
audit chain prefixes and decrypts/checks every ready report and evidence object.
It removes only its own temporary containers/network and preserves the source
volumes plus encrypted backup/result under ignored `.artifacts/restore-*/`.
The restore script rejects other target database/host names. Errors are redacted.

The measured RTO is elapsed restore/verification time after backup creation; RPO
is reported as the age of the latest restored audit record at the simulated failure.
That age also includes quiet periods and is **not a measurement of lost writes**.
Checkpoint age is reported independently. This on-demand drill does not establish
scheduled backups, continuous WAL/PITR, production RPO, off-site durability or cloud
availability. The local bundle is limited to 256 MiB and 10,000 objects; larger
datasets require a reviewed streaming production backup implementation.

Restore failure: keep source services/volumes intact, retain encrypted evidence,
check key custody and isolated target health, and repeat with a fresh target.
Never restore over the source database or reverse append-only security migrations.
Production restore approval requires a separate environment, reconciliation plan,
customer continuity procedures and a documented human go/no-go.

Sprint 12 verification also checks restored subscription count equals organisation
count, reports catalog/term/draft/ticket/event counts, and actually attempts a forbidden
catalog update as the restored database owner inside a rolled-back transaction. This
guard probe refuses every target except isolated `sii_restore` on `restore-db`; it
never runs against the source. Original ciphertext/audit prefixes remain checked.
