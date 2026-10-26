# Evidence reports

Reports are local synthetic evidence, never a food-safety verdict. Owners, site
admins, QA, operations and auditors may request/download within exact current site
grants. Operators and platform staff without a customer grant cannot export. Scope
is checked before counts, jobs, artifacts or grants are disclosed.

POST `.../sites/{site}/reports/` with explicit-offset `start`, exclusive `end`,
`format` (`pdf`/`csv`), `locale` (`en`/`da`) and optional exact-site `zone`.
Maximum 31 days, 800 sensors and 10,000 records per evidence section; at most three
queued/running jobs per site. Oversized requests fail explicitly. No year-long
request is silently sampled/truncated. Reduce window/zone. Workers process one job
at a time, use five-minute leases, expose failures and allow three explicit attempts.
Retries preserve request time, configuration and the immutable source snapshot.

PDF contains a coverage summary and complete raw appendix. CSV uses fixed
`record_type,canonical_json` columns: metadata, readings, coverage, timing policies,
rules, activation boundaries and incident chronology. JSON cells start with object
delimiters, preventing spreadsheet formulas from labels. PDF text is escaped; no
remote fonts/images/resources. Source hash covers canonical snapshot before adding
`source_hash`; artifact SHA-256 covers downloaded bytes. PDF metadata uses a fixed
creation date for deterministic retries; actual receipt cutoff is printed inside.

Configuration labels/cadence/calibration records and incident-event identifiers are
captured at request time. Readings must have been received by the cutoff. Later
backdated observations/events cannot enter retries. Incident history is chronology
through cutoff, not today's mutable response status. Calibration IDs/warnings on each
reading preserve qualification at ingestion. Raw UTC times retain observation/receipt
provenance; PDF window uses site IANA timezone and explicit offsets including DST.
Manual imports and clock-ahead/unqualified readings remain raw evidence but cannot
fill qualified slots. Repeated readings in one slot count once. Missing slots are
explicit gap runs; no interpolation. Qualified percentage is unknown unless approved
matching cadence covers the full window. Expected count is a captured-cadence estimate.

Artifacts use authenticated encrypted private S3 and UUID scope paths. POST
`reports/{job}/access/` issues a five-minute identity-bound single-use grant. GET
`reports/{job}/downloads/{grant}/` also requires current authorization, checks integrity
and audits access. No public S3 URLs. Responses use no-store, nosniff, sandbox and
attachment headers. Availability expires 24 hours after request. Expired ciphertext
and immutable metadata remain in local storage for reviewed retention/backup handling,
not silent deletion. Production retention/key lifecycle require customer/legal approval.

`python scripts/dev.py report-smoke` checks actual independent-worker PDF/CSV,
encryption, checksum and grants in reserved demo scope. Jobs/history remain; a sample
PDF is written to container scratch for visual QA. Generated contracts/migrations
use development commands; hand-written SQL guards protect raw/bulk tenant scope and
immutable evidence. Docstrings/JSDoc and behavior tests were reviewed.
