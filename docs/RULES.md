# Rules and incident evidence

Sprint 06 is synthetic development only. No default temperature limits are supplied.
Rules require an explicit SOP reference, qualified zone sensors and current QA timing
approval. The reserved rapid_change class has no evaluator because no qualified
adapter profile exists. Hardware/site activation remains blocked independently.

## Lifecycle

At `/rules`, an exact-site manager or QA author creates one temperature family per
zone and immutable numbered versions. Changes create new versions; PATCH/DELETE are
unavailable and database triggers preserve evidence. A bounded historical preview
stores input hashes, excluded counts, transitions and qualification/timing snapshots.
It uses source timestamps, excludes manual/skewed/unqualified data, and can inspect
historical backfill without producing live incidents.

QA approval requires the actual site QA role, recent MFA and a selected preview with
at least two qualified inputs. This checks usable input, not scenario completeness
or food safety; reviewers must examine sustained/recovery/gap cases. Ownership is
not QA authority. Management then activates with recent MFA. The server records an
immediate effective boundary; each newer activation ends the previous half-open
interval. Old versions cannot reactivate; future scheduling is not accepted. Changed
cadence, timing policy or qualification fails approval currency checks.

## Evaluation

The pure engine requires consecutive evidence spanning the configured duration and
at least `ceil(duration / interval) + 1` samples. Gaps beyond interval plus grace
reset candidate/recovery timing. Warm/cold episodes are separate; recovery requires
the hysteresis interior for the recovery duration. No outcome declares food safe.

The worker locks the gateway, evaluates each input once and commits evaluation,
incident evidence and outbox completion together. Crashes roll back that unit; retry
cannot duplicate an incident. One unresolved episode per gateway/sensor/classification
is database enforced. Late observations cannot rewind cursors; backfill and delayed
superseded-version input are evidence only. Recovery adds an event and recovered_at;
human status remains open. Human transitions are Sprint 08.

The independent watcher produces separate no-data/offline episodes after approved
initial grace without threshold input. Quarantine produces gateway-scoped invalid
reading evidence without trusting a rejected sensor identifier. Repeated signals
retain one unresolved episode rather than flooding it.

## Scope and maintenance

Maintenance requires actor, reason, exact site, optional sensor, explicit-offset
start and expiry within 24 hours. It never hides readings/incidents. Events preserve
the applicable window/expiry; notification suppression belongs to Sprint 07.
Expired windows remain visible.

All routes are under `/api/v1/organisations/{org}/sites/{site}/`: rule-families,
rule-versions, per-version backtests/approve/activate, maintenance, incidents and
incident events. Current grants precede identifier lookup/pagination. Composite FKs
protect tenant/site scope in raw writes. Evidence is append-only; cursors are mutable
projections. DB-owner bypass remains a hardening concern. No dependency was added.

Regenerate migrations with Django and contracts with `python scripts/dev.py contracts`.
The handwritten SQL guard migration documents its own purpose. Preserve evidence
and volumes on rollback; do not reverse migrations against customer data.
