/** Scoped synthetic readings, explicit freshness failures and raw-derived hourly graphs. */
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import type { components } from "../../../../packages/api-contracts/schema";
import {
  api,
  collection,
  type Organisation,
  type Site,
  type Page,
} from "../api/identity";
import { useLocale } from "../i18n/LocaleProvider";
import { useIdentity, useIdentityMessages } from "./Identity";

type Schema = components["schemas"];
type State = Schema["State"];
type Point = Schema["SeriesPoint"];
const messages = {
  en: {
    retry: "Retry",
    raw: "Inspect raw observations",
    previous: "Previous page",
    next: "Next page",
    source: "Source",
    hide: "Hide secret",
    title: "Readings and freshness",
    notice:
      "Synthetic data only. Fresh data is not a food-safety decision or active site approval.",
    all: "All permitted sites",
    allZones: "All zones",
    cadence: "Configured sample interval (seconds)",
    empty: "No projected readings yet. Missing data is unknown, never healthy.",
    zone: "Zone",
    sensor: "Sensor",
    value: "Last observation",
    observed: "Observed",
    received: "Received",
    state: "Freshness",
    gateway: "Gateway",
    quality: "Quality flags",
    chart: "Hourly raw-data aggregates",
    count: "Samples",
    imports: "Imported",
    flagged: "Flagged",
    average: "Mean °C",
    minimum: "Minimum °C",
    maximum: "Maximum °C",
    gap: "No data",
    start: "Start (UTC)",
    end: "End (UTC)",
    apply: "Apply range",
    range:
      "Up to 31 days. Empty hours remain gaps; boundary hours may be partial.",
    policy: "QA timing approval",
    grace: "Sensor grace (seconds)",
    timeout: "Gateway timeout (seconds)",
    sop: "SOP reference",
    approve: "Approve timing",
    step: "Sensitive actions require recent MFA verification.",
    saved: "Saved. The independent watcher refreshes within 15 seconds.",
    credential: "Device credentials and manual import",
    issue: "Issue 30-day credential",
    revoke: "Revoke",
    once: "Copy this secret now. It is shown only once; never put it in a URL.",
    csv: "CSV content",
    preview: "Preview",
    commit: "Import reviewed rows",
    manual:
      "Imports are manual evidence and never establish live freshness. Each row is revalidated on commit.",
    mapping: "Column mapping",
    choose: "Select a column",
    result: "Row results",
    importId: "Import reference",
    latency: "Processing P95 (last 24 hours)",
    latencyDetail:
      "Server receipt to processing; excludes device/backfill age. Pending work is not included.",
    fresh: "Fresh synthetic data",
    stale: "Sensor stale",
    gateway_offline: "Gateway offline",
    no_data: "No data",
    unqualified: "Device unqualified",
    policy_missing: "Timing not approved",
    quality_warning: "Quality warning",
    watcher_delayed: "Watcher delayed",
    unknown: "Unknown",
    online: "Online",
    offline: "Offline",
  },
  da: {
    retry: "Prøv igen",
    raw: "Se rå observationer",
    previous: "Forrige side",
    next: "Næste side",
    source: "Kilde",
    hide: "Skjul hemmelighed",
    title: "Målinger og aktualitet",
    notice:
      "Kun syntetiske data. Aktuelle data er ikke en fødevaresikkerhedsbeslutning eller godkendt overvågning.",
    all: "Alle tilladte steder",
    allZones: "Alle zoner",
    cadence: "Konfigureret måleinterval (sekunder)",
    empty:
      "Ingen projicerede målinger endnu. Manglende data er ukendt, aldrig sundt.",
    zone: "Zone",
    sensor: "Sensor",
    value: "Seneste observation",
    observed: "Observeret",
    received: "Modtaget",
    state: "Aktualitet",
    gateway: "Gateway",
    quality: "Kvalitetsmarkeringer",
    chart: "Timeaggregater fra rådata",
    count: "Målinger",
    imports: "Importerede",
    flagged: "Markerede",
    average: "Gennemsnit °C",
    minimum: "Minimum °C",
    maximum: "Maksimum °C",
    gap: "Ingen data",
    start: "Start (UTC)",
    end: "Slut (UTC)",
    apply: "Anvend periode",
    range:
      "Højst 31 dage. Tomme timer vises som huller; grænsetimer kan være delvise.",
    policy: "QA-godkendelse af tidsgrænser",
    grace: "Sensorfrist (sekunder)",
    timeout: "Gatewayfrist (sekunder)",
    sop: "SOP-reference",
    approve: "Godkend tidsgrænser",
    step: "Følsomme handlinger kræver nylig MFA-bekræftelse.",
    saved: "Gemt. Den uafhængige overvåger opdaterer inden for 15 sekunder.",
    credential: "Enhedsadgang og manuel import",
    issue: "Udsted 30-dages adgang",
    revoke: "Tilbagekald",
    once: "Kopiér hemmeligheden nu. Den vises kun én gang; brug den aldrig i en URL.",
    csv: "CSV-indhold",
    preview: "Forhåndsvis",
    commit: "Importér gennemgåede rækker",
    manual:
      "Import er manuel dokumentation og etablerer aldrig live-aktualitet. Hver række valideres igen ved import.",
    mapping: "Kolonnetilknytning",
    choose: "Vælg en kolonne",
    result: "Rækkeresultater",
    importId: "Importreference",
    latency: "Behandlings-P95 (seneste 24 timer)",
    latencyDetail:
      "Servermodtagelse til behandling; enheds- og efterleveringsalder er udeladt. Ventende arbejde er ikke inkluderet.",
    fresh: "Aktuelle syntetiske data",
    stale: "Sensor forældet",
    gateway_offline: "Gateway offline",
    no_data: "Ingen data",
    unqualified: "Enhed ikke kvalificeret",
    policy_missing: "Tidsgrænser ikke godkendt",
    quality_warning: "Kvalitetsadvarsel",
    watcher_delayed: "Overvåger forsinket",
    unknown: "Ukendt",
    online: "Online",
    offline: "Offline",
  },
};
type Copy = typeof messages.en;
const qualityCopy: Record<string, [string, string]> = {
  calibration_unknown: ["Calibration unknown", "Kalibrering ukendt"],
  calibration_expired: ["Calibration expired", "Kalibrering udløbet"],
  placement_unqualified: [
    "Placement unqualified",
    "Placering ikke kvalificeret",
  ],
  device_retired: ["Device retired", "Enhed udfaset"],
  device_not_commissioning: ["Device not commissioned", "Enhed ikke idriftsat"],
  facility_archived: ["Facility archived", "Facilitet arkiveret"],
  synthetic: ["Synthetic", "Syntetisk"],
  late_backfill: ["Buffered late data", "Forsinkede bufferdata"],
  clock_ahead: ["Device clock ahead", "Enhedens ur er foran"],
  recent_clock_ahead: ["Recent clock skew", "Nylig urafvigelse"],
  manual_import: ["Manual import", "Manuel import"],
  timing_not_approved: ["Timing not approved", "Tidsgrænser ikke godkendt"],
  recent_gateway_rejections: [
    "Recent rejected gateway data",
    "Nyligt afviste gatewaydata",
  ],
};

/** Localize known quality evidence while leaving unexpected states explicitly unknown. */
function qualityLabel(code: unknown, locale: "en" | "da") {
  return typeof code === "string"
    ? (qualityCopy[code]?.[locale === "en" ? 0 : 1] ?? messages[locale].unknown)
    : messages[locale].unknown;
}

/** Translate known status codes; unknown server states remain explicitly unknown. */
function statusLabel(status: string, t: Copy) {
  return [
    "fresh",
    "stale",
    "gateway_offline",
    "no_data",
    "unqualified",
    "policy_missing",
    "quality_warning",
    "watcher_delayed",
    "online",
    "offline",
  ].includes(status)
    ? t[status as keyof Copy]
    : t.unknown;
}

/** Keep null distinct from a valid numeric zero in every table and tooltip. */
export function readingValue(
  value: string | number | null | undefined,
  locale: string,
) {
  return value === null || value === undefined
    ? "—"
    : new Intl.NumberFormat(locale, { maximumFractionDigits: 4 }).format(
        Number(value),
      );
}

/** Format each instant in the authorized site's IANA zone, including its UTC offset at DST folds. */
export function localTime(
  value: string | null,
  zone: string | undefined,
  locale: string,
) {
  if (!zone) return "—";
  return value
    ? new Intl.DateTimeFormat(locale, {
        dateStyle: "short",
        timeStyle: "long",
        timeZone: zone,
      }).format(new Date(value))
    : "—";
}

/** Reject anonymous rendering before any tenant data request is issued. */
export function MonitoringPage() {
  const { user, loading } = useIdentity();
  const identity = useIdentityMessages();
  if (loading) return <p role="status">{identity.loading}</p>;
  if (!user)
    return (
      <p>
        <Link to="/login">{identity.signInFirst}</Link>
      </p>
    );
  return <Selection key={user.id} />;
}

/** Cross-site selection uses only granted site results, with scope-specific React query keys. */
function Selection() {
  const { user } = useIdentity();
  const { locale } = useLocale();
  const t = messages[locale];
  const identity = useIdentityMessages();
  const [orgId, setOrg] = useState("");
  const [siteId, setSite] = useState("");
  const orgs = useQuery({
    queryKey: ["monitor-orgs", user?.id],
    queryFn: () => collection<Organisation>("/api/v1/organisations/"),
  });
  const org = orgs.data?.find((o) => o.id === orgId) ?? orgs.data?.[0];
  const sites = useQuery({
    queryKey: ["monitor-sites", user?.id, org?.id],
    enabled: !!org,
    queryFn: () => collection<Site>(`/api/v1/organisations/${org?.id}/sites/`),
  });
  const selected = siteId
    ? sites.data?.filter((s) => s.id === siteId)
    : sites.data;
  return (
    <>
      <h1>{t.title}</h1>
      <p role="note">{t.notice}</p>
      {(orgs.isError || sites.isError) && <p role="alert">{identity.failed}</p>}
      <div className="admin-form">
        <label className="form-field">
          {identity.organisation}
          <select
            value={org?.id ?? ""}
            onChange={(e) => {
              setOrg(e.target.value);
              setSite("");
            }}
          >
            {orgs.data?.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
        </label>
        <label className="form-field">
          {identity.site}
          <select value={siteId} onChange={(e) => setSite(e.target.value)}>
            <option value="">{t.all}</option>
            {sites.data?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {selected?.map((site) => (
        <SiteMonitor key={site.id} site={site} />
      ))}
    </>
  );
}

/** Poll projections separately from graph data; a failed refresh hides cached freshness claims. */
function SiteMonitor({ site }: { site: Site }) {
  const { user } = useIdentity();
  const { locale } = useLocale();
  const t = messages[locale];
  const identity = useIdentityMessages();
  const base = `/api/v1/organisations/${site.organisation}/sites/${site.id}/`;
  const [sensor, setSensor] = useState("");
  const [zone, setZone] = useState("");
  const query = useQuery({
    queryKey: ["monitor", user?.id, site.id],
    queryFn: () => collection<State>(base + "monitoring/"),
    refetchInterval: 15000,
    retry: false,
  });
  const roles =
    user?.memberships
      .find((m) => m.organisation === site.organisation)
      ?.roles.filter((r) => r.site === site.id || r.role === "owner")
      .map((r) => r.role) ?? [];
  const latency = useQuery({
    queryKey: ["latency", user?.id, site.id],
    queryFn: () => api<Schema["LatencyResult"]>(base + "latency/"),
    refetchInterval: 30000,
  });
  const filtered = query.data?.filter((s) => !zone || s.zone === zone);
  const selected = filtered?.find((s) => s.sensor === sensor) ?? filtered?.[0];
  return (
    <section className="workspace">
      <h2>{site.name}</h2>
      <p>{site.timezone}</p>
      {query.isError ? (
        <p role="alert">
          {identity.failed}{" "}
          <button onClick={() => void query.refetch()}>{t.retry}</button>
        </p>
      ) : query.isPending ? (
        <p role="status">{identity.loading}</p>
      ) : (
        <>
          {!query.data?.length && <p>{t.empty}</p>}
          <label className="form-field">
            {t.zone}
            <select
              value={zone}
              onChange={(e) => {
                setZone(e.target.value);
                setSensor("");
              }}
            >
              <option value="">{t.allZones}</option>
              {[...new Set(query.data?.map((s) => s.zone))].map((name) => (
                <option key={name}>{name}</option>
              ))}
            </select>
          </label>
          <div className="monitor-grid">
            {filtered?.map((state) => (
              <article className="monitor-card" key={state.sensor}>
                <h3>
                  <button
                    onClick={() => setSensor(state.sensor)}
                    aria-pressed={selected?.sensor === state.sensor}
                  >
                    {state.name}
                  </button>
                </h3>
                <p>{state.zone}</p>
                <p className="reading-value">
                  {readingValue(state.reading?.value, locale)}{" "}
                  {state.reading?.unit === "degC" ? "°C" : ""}
                </p>
                <p>
                  <span
                    className={`status ${state.current_status === "fresh" ? "" : "error"}`}
                  >
                    {statusLabel(state.current_status, t)}
                  </span>
                </p>
                <dl>
                  <dt>{t.gateway}</dt>
                  <dd>{statusLabel(state.gateway_status, t)}</dd>
                  <dt>{t.observed}</dt>
                  <dd>
                    {localTime(
                      state.reading?.observed_at ?? null,
                      site.timezone,
                      locale,
                    )}
                  </dd>
                  <dt>{t.received}</dt>
                  <dd>
                    {localTime(state.last_received_at, site.timezone, locale)}
                  </dd>
                </dl>
                <p>
                  {t.quality}:{" "}
                  {Array.isArray(state.quality)
                    ? state.quality
                        .map((flag) => qualityLabel(flag, locale))
                        .join(", ")
                    : t.unknown}
                </p>
              </article>
            ))}
          </div>
          {selected && (
            <Series
              key={selected.sensor}
              base={base}
              state={selected}
              site={site}
            />
          )}
        </>
      )}
      <p>
        {t.latency}:{" "}
        {latency.isError
          ? t.unknown
          : readingValue(latency.data?.p95_processing_seconds, locale)}{" "}
        s ({latency.data?.samples ?? 0} {t.count.toLowerCase()})
      </p>
      <p>{t.latencyDetail}</p>
      {roles.includes("qa") && <PolicyForm base={base} />}
      {roles.some((r) => ["owner", "site_admin"].includes(r)) && (
        <ImportPanel base={base} />
      )}
    </section>
  );
}

/** Graph raw-derived buckets independently; empty buckets have no mark or connecting line. */
function Series({
  base,
  state,
  site,
}: {
  base: string;
  state: State;
  site: Site;
}) {
  const { locale } = useLocale();
  const t = messages[locale];
  const identity = useIdentityMessages();
  const [range, setRange] = useState(() => ({
    start: new Date(Date.now() - 86400000).toISOString().slice(0, 16),
    end: new Date().toISOString().slice(0, 16),
  }));
  const query = useQuery({
    queryKey: ["series", base, state.sensor, range],
    queryFn: () =>
      api<Schema["SeriesResult"]>(
        base +
          "series/?" +
          new URLSearchParams({
            sensor: state.sensor,
            start: range.start + ":00Z",
            end: range.end + ":00Z",
          }),
      ),
    retry: false,
  });
  const points = query.data?.points ?? [];
  const values = points.flatMap((p) =>
    p.minimum === null ? [] : [Number(p.minimum), Number(p.maximum)],
  );
  const low = values.length ? Math.min(...values) - 1 : -1;
  const high = values.length ? Math.max(...values) + 1 : 1;
  /** Map values to the fixed SVG viewport without a truthiness check that would erase zero. */
  const y = (value: string | null) =>
    140 - ((Number(value) - low) / (high - low)) * 120;
  /** Interpret inputs as explicitly labeled UTC; the server verifies offsets and range bounds. */
  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    setRange({ start: String(f.get("start")), end: String(f.get("end")) });
  }
  return (
    <section>
      <h3>
        {t.chart}: {state.name}
      </h3>
      <p>{t.range}</p>
      <p>
        {t.cadence}: {query.data?.expected_interval_sec ?? "—"}
      </p>
      <form className="admin-form" onSubmit={apply}>
        <label className="form-field">
          {t.start}
          <input
            type="datetime-local"
            name="start"
            defaultValue={range.start}
            required
          />
        </label>
        <label className="form-field">
          {t.end}
          <input
            type="datetime-local"
            name="end"
            defaultValue={range.end}
            required
          />
        </label>
        <button>{t.apply}</button>
      </form>
      {query.isError ? (
        <p role="alert">{identity.failed}</p>
      ) : query.isPending ? (
        <p>{identity.loading}</p>
      ) : (
        <>
          <svg
            viewBox="0 0 720 170"
            className="series-chart"
            role="img"
            aria-label={t.chart}
          >
            <title>{t.chart}</title>
            <text x="0" y="14">
              {readingValue(high, locale)} °C
            </text>
            <text x="0" y="160">
              {readingValue(low, locale)} °C
            </text>
            {points.map((p: Point, index) =>
              p.average === null ? null : (
                <g key={p.start}>
                  <title>
                    {localTime(p.start, site.timezone, locale)}: {p.average} °C;{" "}
                    {p.count} {t.count}
                  </title>
                  <line
                    x1={50 + (index / Math.max(points.length, 1)) * 650}
                    x2={50 + (index / Math.max(points.length, 1)) * 650}
                    y1={y(p.minimum)}
                    y2={y(p.maximum)}
                    stroke="currentColor"
                    strokeWidth="3"
                  />
                  <circle
                    cx={50 + (index / Math.max(points.length, 1)) * 650}
                    cy={y(p.average)}
                    r="3"
                    fill="currentColor"
                  />
                </g>
              ),
            )}
          </svg>
          <div className="table-scroll">
            <table>
              <caption>
                {t.chart} · {site.timezone}
              </caption>
              <thead>
                <tr>
                  {[
                    t.start,
                    t.count,
                    t.average,
                    t.minimum,
                    t.maximum,
                    t.imports,
                    t.flagged,
                  ].map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {points.map((p) => (
                  <tr key={p.start}>
                    <td>{localTime(p.start, site.timezone, locale)}</td>
                    <td>{p.count || t.gap}</td>
                    <td>{readingValue(p.average, locale)}</td>
                    <td>{readingValue(p.minimum, locale)}</td>
                    <td>{readingValue(p.maximum, locale)}</td>
                    <td>{p.imported}</td>
                    <td>{p.flagged}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <RawHistory
            key={range.start + range.end}
            base={base}
            sensor={state.sensor}
            site={site}
            range={range}
          />
        </>
      )}
    </section>
  );
}

/** Inspect bounded raw pages for the exact graph window; never download an unbounded trace. */
function RawHistory({
  base,
  sensor,
  site,
  range,
}: {
  base: string;
  sensor: string;
  site: Site;
  range: { start: string; end: string };
}) {
  const { locale } = useLocale();
  const t = messages[locale];
  const identity = useIdentityMessages();
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ["raw-history", base, sensor, range, page],
    enabled: open,
    retry: false,
    queryFn: () =>
      api<Page<Schema["Reading"]>>(
        base +
          "readings/?" +
          new URLSearchParams({
            sensor,
            start: range.start + ":00Z",
            end: range.end + ":00Z",
            page: String(page),
          }),
      ),
  });
  return (
    <details onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>{t.raw}</summary>
      {query.isError ? (
        <p role="alert">{identity.failed}</p>
      ) : query.isPending ? (
        <p>{identity.loading}</p>
      ) : (
        <>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t.observed}</th>
                  <th>{t.received}</th>
                  <th>°C</th>
                  <th>{t.source}</th>
                  <th>{t.quality}</th>
                </tr>
              </thead>
              <tbody>
                {query.data?.results.map((row) => (
                  <tr key={row.id}>
                    <td>{localTime(row.observed_at, site.timezone, locale)}</td>
                    <td>{localTime(row.received_at, site.timezone, locale)}</td>
                    <td>{readingValue(row.value, locale)}</td>
                    <td>
                      {qualityLabel(
                        row.source === "simulator"
                          ? "synthetic"
                          : "manual_import",
                        locale,
                      )}
                    </td>
                    <td>
                      {Array.isArray(row.quality)
                        ? row.quality
                            .map((flag) => qualityLabel(flag, locale))
                            .join(", ")
                        : t.unknown}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!query.data?.count && <p>{t.gap}</p>}
          <button disabled={page === 1} onClick={() => setPage(page - 1)}>
            {t.previous}
          </button>
          <button
            disabled={!query.data?.next}
            onClick={() => setPage(page + 1)}
          >
            {t.next}
          </button>
        </>
      )}
    </details>
  );
}

/** Fresh QA approval creates immutable timing evidence; owner access alone never shows this form. */
function PolicyForm({ base }: { base: string }) {
  const t = messages[useLocale().locale];
  const identity = useIdentityMessages();
  const [message, setMessage] = useState("");
  /** Let the server snapshot current cadence and verify the caller's recent MFA. */
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    try {
      await api(base + "freshness-policy/", "POST", {
        sensor_grace_sec: Number(f.get("grace")),
        gateway_timeout_sec: Number(f.get("timeout")),
        sop_reference: f.get("sop"),
      });
      setMessage(t.saved);
    } catch {
      setMessage(identity.failed);
    }
  }
  return (
    <details>
      <summary>{t.policy}</summary>
      <p>
        <Link to="/security">{t.step}</Link>
      </p>
      <form className="admin-form" onSubmit={(e) => void submit(e)}>
        <label className="form-field">
          {t.grace}
          <input name="grace" type="number" min="0" max="86400" required />
        </label>
        <label className="form-field">
          {t.timeout}
          <input name="timeout" type="number" min="10" max="86400" required />
        </label>
        <label className="form-field">
          {t.sop}
          <input name="sop" maxLength={240} required />
        </label>
        <button>{t.approve}</button>
      </form>
      <p role="status">{message}</p>
    </details>
  );
}

/** Parse one CSV header with escaped quotes, leaving full row validation to the server. */
export function csvHeaders(text: string): string[] {
  const result: string[] = [];
  let value = "",
    quoted = false;
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (char === '"') {
      if (quoted && text[i + 1] === '"') {
        value += '"';
        i++;
      } else quoted = !quoted;
    } else if (!quoted && (char === "\n" || char === "\r")) break;
    else if (!quoted && char === ",") {
      result.push(value);
      value = "";
    } else value += char;
  }
  return [...result, value].filter(Boolean);
}

/** Manager-only one-time credential display and preview-before-commit manual import workflow. */
function ImportPanel({ base }: { base: string }) {
  const t = messages[useLocale().locale];
  const identity = useIdentityMessages();
  const [secret, setSecret] = useState("");
  const [csv, setCSV] = useState("");
  const [credential, setCredential] = useState("");
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [importId] = useState(() => crypto.randomUUID());
  const [preview, setPreview] = useState<Schema["CSVResult"] | null>(null);
  const [message, setMessage] = useState("");
  const credentials = useQuery({
    queryKey: ["device-credentials", base],
    queryFn: () =>
      collection<Schema["Credential"]>(base + "device-credentials/"),
  });
  const gateways = useQuery({
    queryKey: ["import-gateways", base],
    queryFn: () => collection<Schema["Gateway"]>(base + "gateways/"),
  });
  /** Show issued secret once in memory, refreshing only non-secret credential metadata. */
  async function issue(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSecret("");
    try {
      const issued = await api<Schema["IssuedCredential"]>(
        base + "device-credentials/",
        "POST",
        { gateway: new FormData(event.currentTarget).get("gateway"), days: 30 },
      );
      setSecret(`${issued.id}.${issued.secret}`);
      await credentials.refetch();
    } catch {
      setMessage(identity.failed);
    }
  }
  /** Commit exactly the previewed mapping/text; editing either invalidates the preview below. */
  async function importRows(commit: boolean) {
    try {
      setPreview(
        await api<Schema["CSVResult"]>(base + "csv-import/", "POST", {
          credential,
          csv,
          mapping,
          import_id: importId,
          preview: !commit,
        }),
      );
      setMessage(commit ? t.saved : "");
    } catch {
      setMessage(identity.failed);
      setPreview(null);
    }
  }
  return (
    <details>
      <summary>{t.credential}</summary>
      <p>
        <Link to="/security">{t.step}</Link>
      </p>
      <form className="admin-form" onSubmit={(e) => void issue(e)}>
        <label className="form-field">
          {t.gateway}
          <select name="gateway" required>
            {gateways.data?.map((g) => (
              <option value={g.id} key={g.id}>
                {g.name}
              </option>
            ))}
          </select>
        </label>
        <button>{t.issue}</button>
      </form>
      {secret && (
        <div role="status">
          <p>{t.once}</p>
          <textarea readOnly value={secret} aria-label={t.once} />
          <button onClick={() => setSecret("")}>{t.hide}</button>
        </div>
      )}
      <label className="form-field">
        {t.credential}
        <select
          value={credential}
          onChange={(e) => {
            setCredential(e.target.value);
            setPreview(null);
          }}
        >
          <option value="">{t.choose}</option>
          {credentials.data
            ?.filter(
              (c) =>
                c.provisioned &&
                !c.revoked_at &&
                new Date(c.expires_at) > new Date(),
            )
            .map((c) => (
              <option key={c.id} value={c.id}>
                {c.id.slice(0, 8)} ·{" "}
                {gateways.data?.find((g) => g.id === c.gateway)?.name}
              </option>
            ))}
        </select>
      </label>
      {credential && (
        <button
          onClick={() =>
            void api(base + `device-credentials/${credential}/revoke/`, "POST")
              .then(() => {
                setCredential("");
                setPreview(null);
                return credentials.refetch();
              })
              .catch(() => setMessage(identity.failed))
          }
        >
          {t.revoke}
        </button>
      )}
      <p>{t.manual}</p>
      <label className="form-field">
        {t.csv}
        <textarea
          rows={5}
          maxLength={60000}
          value={csv}
          onChange={(e) => {
            setCSV(e.target.value);
            setPreview(null);
          }}
        />
      </label>
      <fieldset>
        <legend>{t.mapping}</legend>
        {["sensor_id", "observed_at", "value", "unit"].map((field) => (
          <label className="form-field" key={field}>
            {field}
            <select
              value={mapping[field] ?? ""}
              onChange={(e) => {
                setMapping({ ...mapping, [field]: e.target.value });
                setPreview(null);
              }}
            >
              <option value="">{t.choose}</option>
              {csvHeaders(csv).map((header) => (
                <option key={header}>{header}</option>
              ))}
            </select>
          </label>
        ))}
      </fieldset>
      <button
        disabled={
          !credential || Object.values(mapping).filter(Boolean).length !== 4
        }
        onClick={() => void importRows(false)}
      >
        {t.preview}
      </button>
      {preview && (
        <>
          <p>
            {t.result} · {t.importId}: {importId}
          </p>
          <ul>
            {preview.rows.map((row, index) => (
              <li key={index}>
                {String(row.row)}: {String(row.status)}{" "}
                {typeof row.reason === "string" ? row.reason : ""}
              </li>
            ))}
          </ul>
          <button
            disabled={!preview.rows.some((r) => r.status === "valid")}
            onClick={() => void importRows(true)}
          >
            {t.commit}
          </button>
        </>
      )}
      <p role="status">{message}</p>
    </details>
  );
}
