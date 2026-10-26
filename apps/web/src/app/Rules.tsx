/** Immutable rule authoring and historical previews. No default safety limits or live-site claims. */
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "../../../../packages/api-contracts/schema";
import { api, collection } from "../api/identity";
import { useLocale } from "../i18n/LocaleProvider";
import { Field, useIdentityMessages } from "./Identity";
import { ScopedWorkspace, type WorkspaceScope } from "./ScopedWorkspace";

type Schema = components["schemas"];
const messages = {
  en: {
    title: "Rules and incident evidence",
    notice:
      "Synthetic only. QA approval is required before activation. Recovery does not close an incident or declare food safe.",
    family: "Create zone rule family",
    zone: "Zone",
    name: "Name",
    version: "Create immutable version",
    lower: "Lower limit (°C)",
    upper: "Upper limit (°C)",
    hysteresis: "Hysteresis (°C)",
    sustained: "Sustained breach (seconds)",
    recovery: "Recovery (seconds)",
    sop: "SOP reference",
    create: "Create",
    history: "Version history",
    preview: "Run historical preview",
    start: "Start (UTC)",
    end: "End (UTC)",
    approve: "QA: approve reviewed preview",
    activate: "Activate synthetic version",
    maintenance: "Visible maintenance window",
    reason: "Reason",
    sitewide: "Entire selected site",
    sensor: "Sensor",
    save: "Save expiring window",
    evidence: "Incident evidence",
    open: "Human response status",
    recovered: "Recovery observed",
    absent: "Not observed",
    step: "Verify MFA for sensitive actions",
    empty: "No records",
    previewResult: "Preserved preview result",
    stages: {
      draft: "Draft",
      tested: "Tested",
      approved: "QA approved",
      active_synthetic: "Active — synthetic",
      superseded: "Superseded",
    },
  },
  da: {
    title: "Regler og hændelsesdokumentation",
    notice:
      "Kun syntetisk. QA-godkendelse kræves før aktivering. Genopretning lukker ikke hændelsen eller erklærer fødevarer sikre.",
    family: "Opret regelfamilie for zone",
    zone: "Zone",
    name: "Navn",
    version: "Opret uforanderlig version",
    lower: "Nedre grænse (°C)",
    upper: "Øvre grænse (°C)",
    hysteresis: "Hysterese (°C)",
    sustained: "Vedvarende overskridelse (sekunder)",
    recovery: "Genopretning (sekunder)",
    sop: "SOP-reference",
    create: "Opret",
    history: "Versionshistorik",
    preview: "Kør historisk forhåndsvisning",
    start: "Start (UTC)",
    end: "Slut (UTC)",
    approve: "QA: godkend gennemgået forhåndsvisning",
    activate: "Aktivér syntetisk version",
    maintenance: "Synligt vedligeholdelsesvindue",
    reason: "Begrundelse",
    sitewide: "Hele det valgte sted",
    sensor: "Sensor",
    save: "Gem tidsbegrænset vindue",
    evidence: "Hændelsesdokumentation",
    open: "Menneskelig responsstatus",
    recovered: "Genopretning observeret",
    absent: "Ikke observeret",
    step: "Bekræft MFA til følsomme handlinger",
    empty: "Ingen poster",
    previewResult: "Gemt forhåndsvisningsresultat",
    stages: {
      draft: "Kladde",
      tested: "Testet",
      approved: "QA-godkendt",
      active_synthetic: "Aktiv — syntetisk",
      superseded: "Erstattet",
    },
  },
};

/** Localize derived version states without implying operational qualification. */
export function ruleStage(stage: string, locale: "en" | "da") {
  return (
    messages[locale].stages[stage as keyof typeof messages.en.stages] ?? stage
  );
}

/** Wrap the builder in the shared authenticated exact-site boundary. */
export function RulesPage() {
  const { locale } = useLocale();
  return (
    <>
      <h1>{messages[locale].title}</h1>
      <p role="note">{messages[locale].notice}</p>
      <ScopedWorkspace>
        {(scope) => <RuleWorkspace key={scope.site.id} {...scope} />}
      </ScopedWorkspace>
    </>
  );
}

/** Native form field accepting explicit finite numeric inputs, including negative temperatures. */
function NumberField({ name, label }: { name: string; label: string }) {
  return (
    <label className="form-field">
      {label}
      <input name={name} type="number" step="any" required />
    </label>
  );
}

/** Preserve draft/preview selection per site; all commands are reauthorized by server and audited. */
function RuleWorkspace({ base, roles }: WorkspaceScope) {
  const { locale } = useLocale();
  const t = messages[locale];
  const identity = useIdentityMessages();
  const cache = useQueryClient();
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<Schema["Backtest"] | null>(null);
  const query = useQuery({
    queryKey: ["rule-workspace", base],
    queryFn: async () => {
      const [families, versions, zones, sensors, maintenance, incidents] =
        await Promise.all([
          collection<Schema["Family"]>(base + "rule-families/"),
          collection<Schema["Version"]>(base + "rule-versions/"),
          collection<Schema["Zone"]>(base + "zones/"),
          collection<Schema["Sensor"]>(base + "sensors/"),
          collection<Schema["Suppression"]>(base + "maintenance/"),
          collection<Schema["Incident"]>(base + "incidents/"),
        ]);
      return { families, versions, zones, sensors, maintenance, incidents };
    },
    retry: false,
  });
  const author = roles.some((role) =>
    ["owner", "site_admin", "qa"].includes(role),
  );
  const manager = roles.some((role) => ["owner", "site_admin"].includes(role));
  /** Serialize UI mutations; errors retain local input and never claim success or approval. */
  async function command(path: string, body?: unknown) {
    setBusy(true);
    setError(false);
    try {
      const result = await api<Schema["Backtest"]>(base + path, "POST", body);
      await cache.invalidateQueries({ queryKey: ["rule-workspace", base] });
      return result;
    } catch {
      setError(true);
      return null;
    } finally {
      setBusy(false);
    }
  }
  /** Read only named native fields; server rejects extra/untrusted scope keys. */
  function fields(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    return Object.fromEntries(new FormData(event.currentTarget));
  }
  if (query.isError) return <p role="alert">{identity.failed}</p>;
  if (!query.data) return <p role="status">{identity.loading}</p>;
  const data = query.data;
  return (
    <>
      {error && <p role="alert">{identity.failed}</p>}
      {author && (
        <>
          <p>
            <Link to="/security">{t.step}</Link>
          </p>
          <section className="workspace">
            <h2>{t.family}</h2>
            <form
              className="admin-form"
              onSubmit={(e) => void command("rule-families/", fields(e))}
            >
              <Field name="name" label={t.name} />
              <label className="form-field">
                {t.zone}
                <select name="zone" required>
                  {data.zones.map((zone) => (
                    <option key={zone.id} value={zone.id}>
                      {zone.name}
                    </option>
                  ))}
                </select>
              </label>
              <button disabled={busy}>{t.create}</button>
            </form>
          </section>
          <section className="workspace">
            <h2>{t.version}</h2>
            <form
              className="admin-form"
              onSubmit={(e) => void command("rule-versions/", fields(e))}
            >
              <label className="form-field">
                {t.family}
                <select name="ruleset" required>
                  {data.families.map((family) => (
                    <option key={family.id} value={family.id}>
                      {family.name}
                    </option>
                  ))}
                </select>
              </label>
              {(
                [
                  ["lower_bound", t.lower],
                  ["upper_bound", t.upper],
                  ["hysteresis", t.hysteresis],
                  ["sustained_sec", t.sustained],
                  ["recovery_sec", t.recovery],
                ] as const
              ).map(([name, label]) => (
                <NumberField key={name} name={name} label={label} />
              ))}
              <Field name="sop_reference" label={t.sop} />
              <button disabled={busy}>{t.create}</button>
            </form>
          </section>
        </>
      )}
      <section className="workspace">
        <h2>{t.history}</h2>
        {data.versions.length === 0 && <p>{t.empty}</p>}
        {data.versions.map((version) => (
          <article key={version.id} className="workspace">
            <h3>
              {
                data.families.find((family) => family.id === version.ruleset)
                  ?.name
              }{" "}
              · v{version.version}
            </h3>
            <p>
              {ruleStage(version.stage, locale)} · {version.lower_bound}–
              {version.upper_bound} °C · {t.hysteresis}: {version.hysteresis} ·{" "}
              {t.sustained}: {version.sustained_sec} · {t.recovery}:{" "}
              {version.recovery_sec}
            </p>
            <p>
              {t.sop}: {version.sop_reference}
            </p>
            {author && (
              <form
                className="admin-form"
                onSubmit={async (e) => {
                  const values = fields(e);
                  const result = await command(
                    `rule-versions/${version.id}/backtests/`,
                    { start: `${values.start}:00Z`, end: `${values.end}:00Z` },
                  );
                  setPreview(result);
                }}
              >
                <Field name="start" label={t.start} type="datetime-local" />
                <Field name="end" label={t.end} type="datetime-local" />
                <button disabled={busy}>{t.preview}</button>
              </form>
            )}
            {preview?.version === version.id && (
              <>
                <h4>{t.previewResult}</h4>
                <pre className="evidence-json">
                  {JSON.stringify(preview.result, null, 2)}
                </pre>
                {roles.includes("qa") && !version.approval && (
                  <button
                    disabled={busy}
                    onClick={() =>
                      void command(`rule-versions/${version.id}/approve/`, {
                        backtest: preview.id,
                      })
                    }
                  >
                    {t.approve}
                  </button>
                )}
              </>
            )}
            {manager && version.stage === "approved" && (
              <button
                disabled={busy}
                onClick={() =>
                  void command(`rule-versions/${version.id}/activate/`)
                }
              >
                {t.activate}
              </button>
            )}
          </article>
        ))}
      </section>
      <section className="workspace">
        <h2>{t.maintenance}</h2>
        {author && (
          <form
            className="admin-form"
            onSubmit={(e) => {
              const values = fields(e);
              void command("maintenance/", {
                ...values,
                sensor: values.sensor || null,
                start: `${values.start}:00Z`,
                end: `${values.end}:00Z`,
              });
            }}
          >
            <label className="form-field">
              {t.sensor}
              <select name="sensor">
                <option value="">{t.sitewide}</option>
                {data.sensors.map((sensor) => (
                  <option key={sensor.id} value={sensor.id}>
                    {sensor.name}
                  </option>
                ))}
              </select>
            </label>
            <Field name="start" label={t.start} type="datetime-local" />
            <Field name="end" label={t.end} type="datetime-local" />
            <Field name="reason" label={t.reason} />
            <button disabled={busy}>{t.save}</button>
          </form>
        )}
        {data.maintenance.map((item) => (
          <p key={item.id}>
            {item.reason} · {item.start} → {item.end} ·{" "}
            {data.sensors.find((sensor) => sensor.id === item.sensor)?.name ??
              t.sitewide}
          </p>
        ))}
      </section>
      <section className="workspace">
        <h2>{t.evidence}</h2>
        {data.incidents.length === 0 && <p>{t.empty}</p>}
        {data.incidents.map((incident) => (
          <p key={incident.id}>
            {incident.kind} · {incident.opened_at} · {t.open}: {incident.status}{" "}
            · {t.recovered}: {incident.recovered_at ?? t.absent}
          </p>
        ))}
      </section>
    </>
  );
}
