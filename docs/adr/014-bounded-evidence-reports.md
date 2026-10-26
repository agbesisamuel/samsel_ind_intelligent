# ADR 014: Bounded immutable evidence exports

Accepted 2026-10-21, Sprint 09. Use a PostgreSQL report queue and independent worker,
immutable request/configuration/snapshot, deterministic ReportLab PDF and typed JSON
CSV records. Bound work explicitly instead of presenting partial exports as complete.
Reuse encrypted private S3; identity-bound expiring grants avoid public bearer links.
Snapshots preserve actual raw quality and unknown cadence coverage. A local export
is not regulatory certification. See REPORTS.md for contracts, limits and retention.
