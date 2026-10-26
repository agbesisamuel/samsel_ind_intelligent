# Freshness and manual evidence — Sprint 05

The dashboard at `/readings` lists only sites the signed-in user is currently
permitted to read. Organisation/site/zone/sensor selection never grants authority.
Cards show observation and receipt clocks, gateway state, current quality flags
and the site's IANA timezone. Numeric zero is displayed as a measurement; null
remains an em dash. Synthetic freshness does not approve a real monitored site.

An explicit site QA role and recent MFA are required to approve a timing policy:
sensor grace, gateway timeout and SOP reference. Approval snapshots registered
sensor intervals and is immutable. A changed interval/new sensor requires a new
approval. Owner/platform privileges do not imply QA. Missing timing approval is
`policy_missing`, never fresh. Current calibration/placement and device lifecycle
also remain relevant; fresh timestamps cannot qualify an unqualified sensor.

The independent `freshness-worker` checks every 15 seconds even if ingestion stops.
Both source observation age and receipt age must fit the approved sensor window.
Gateway heartbeat is checked independently against the QA-approved timeout.
Manual imports, old backfill and clock-ahead samples cannot establish a current
gateway heartbeat. Future-skew records do not become current observations; recent
invalid/clock-ahead traffic is a visible quality warning. Late arrival cannot
replace a newer observed value, but its receipt time remains visible separately.

The API invalidates a projection after 60 seconds without a watcher evaluation:
`watcher_delayed`, gateway `unknown`. Client refresh errors hide cached state claims.
Freshness changes produce append-only evidence, not human incidents. Health is
rebuildable from raw evidence; no temperature recovery closes an incident here.

Series requests require explicit-offset UTC start/end and a sensor within the URL
site, with a positive range no greater than 31 days. Hourly min/max/mean aggregates
derive from raw rows; empty hours are explicit null buckets and have no graph mark.
UTC buckets keep repeated local DST hours distinct. The UI formats them in the
site timezone including offset, shows counts/import/flag counts and registered
cadence, and labels partial boundary hours. Hourly aggregation does not claim
continuous coverage within an hour. Raw paginated evidence remains available in
the scoped readings API. Source/qualification snapshots are not rewritten.

Latency is the exact PostgreSQL continuous P95 of receipt-to-processing seconds
for processed rows received in the last 24 hours, with sample size. It is not
device/network observation delay and excludes pending rows; ingestion metrics
separately expose pending/dead work. Numeric production NFR/load proof remains
Sprint 10 work, not an assumption inferred from a functioning dashboard.

Manual CSV workflow: manager MFA → select same-site credential → map unique input
columns to sensor UUID/time/value/unit → preview each row → commit reviewed rows.
Version/sequence default to protocol v1/row index; a stable import UUID derives
event UUIDs when not mapped. At most 100 rows/60,000 characters; explicit offsets,
units, scope, qualification, range and credential lifecycle are checked in preview
without reading/quarantine/outbox writes. Commit reruns the same checks. Mixed-row
results are explicit and repeated import is idempotent. Imports remain permanently
`manual_import` and are excluded from current feed freshness. Preview is advisory,
not a reservation or a guarantee that changing device state will still pass commit.

APIs: site-scoped `freshness-policy/`, `monitoring/`, `series/`, `latency/`, and
enhanced `csv-import/`. Policy and transition evidence are append-only; projection
scope/related objects are DB guarded. No production/customer approval is synthesized.
