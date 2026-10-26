# Local commercial administration

Sprint 12 implements BILL-01 with synthetic, source-controlled technical templates.
These are capacity defaults, not validated prices, contracts or service promises:

| Template | Active sites | Non-retired probes | Probes/site |
|---|---:|---:|---:|
| local-trial-v1 | 2 | 80 | 40 |
| local-pilot-v1 | 20 | 800 | 40 |
| local-demo-v1 | 100 | 10000 | 1000 |

Every newly inserted organisation receives a subscription in the same database
transaction. Non-demo defaults to a 30-day trial; demo defaults to the local demo
template. Seeded plans are immutable, including against runtime SQL DML. Changing
the catalog requires a reviewed new migration; do not edit generated migrations.
Existing organisations are backfilled without deleting assets or history.

Counts include planned probes; retired probes and archived sites release their
respective quota. Probes in an archived site still count until retired. API and SQL
triggers serialize expansion on the subscription row. Unarchive/unretire checks
capacity again. Expiry uses wall time after waiting for locks. Past-due, ended or
expired terms deny new expansion. Downgrades preserve existing assets and expose
overage warnings. Seven-day term warnings are server-derived.

Commercial terms NEVER suspend existing telemetry, rule evaluation, notifications,
incident response or evidence reads. No payment collection or live activation exists.
An explicit platform commercial administrator with recent MFA may change plan/state/
end and must record a reason; immutable history preserves actor, time and before/
after. This narrow commercial metadata exception grants no ordinary site content.
Owners can view their own usage/history/drafts and amend contact/reference fields
with recent MFA. Operators and other site-only roles cannot read tenant billing.

Manual drafts accept a unique reference, bounded period, DKK/EUR/USD and explicitly
entered nonnegative net/tax amounts. There are no prices, tax rates, exchange rates,
payment methods, card fields, provider destinations or paid status. Identical
reference/content replay is idempotent; changed content is rejected. Drafts cannot
be rewritten or deleted. Owner/platform CSV export rechecks current scope, is audited
and no-store, neutralizes spreadsheet formula prefixes, and marks every row
SYNTHETIC_FINANCE_DRAFT. This is not a legally approved invoice or accounting system.

Demonstration: login as the generated owner and open `/billing`; inspect capacity,
warnings, contact settings and term history. `/help` shows granted-site operational
counts and release gates. `python scripts/dev.py commercial-smoke` creates disjoint
fictional identities and a zero-value draft, performs genuine HTTP MFA and CSV
export, then disables its identities while retaining audit/draft evidence. Never
use actual finance/customer data. Finance/accountant/provider/contract approval and
any automated billing integration remain outside this release.
