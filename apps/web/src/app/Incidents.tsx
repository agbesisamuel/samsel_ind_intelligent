/** Human incident response and immutable chronology; automatic recovery is never human closure. */
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "../../../../packages/api-contracts/schema";
import { api, collection, download, upload } from "../api/identity";
import { useLocale } from "../i18n/LocaleProvider";
import { Field, useIdentityMessages } from "./Identity";
import { ScopedWorkspace, type WorkspaceScope } from "./ScopedWorkspace";
import { localTime } from "./Monitoring";

type Schema = components["schemas"];

/** Validate untyped JSON evidence before rendering text; objects and arrays are never coerced. */
export function evidenceText(
  evidence: unknown,
  key: string,
): string | undefined {
  if (!evidence || typeof evidence !== "object" || Array.isArray(evidence))
    return undefined;
  const value = (evidence as Record<string, unknown>)[key];
  return typeof value === "string" ? value : undefined;
}
const labels = {
  en: {
    title: "Incidents and human response",
    notice:
      "Synthetic evidence only. Recovery does not close an incident. QA review and observed recovery are required for closure; closure is not a food-safety declaration.",
    all: "All states",
    state: "Human response status",
    kind: "Classification",
    opened: "Opened",
    recovered: "Recovery observed",
    none: "Not recorded",
    assigned: "Assigned to",
    timeline: "Immutable timeline",
    attachments: "Evidence attachments",
    file: "UTF-8 text file (maximum 64 KiB)",
    label: "Evidence label",
    attach: "Attach evidence",
    restriction:
      "Only plain .txt evidence is enabled. Active documents, images and archives are rejected.",
    action: "Response action",
    text: "Evidence, reasoning or SOP reference",
    save: "Record action",
    assignee: "Assign responder",
    assign: "Assign",
    export: "Download activity JSON",
    get: "Download",
    providers: "Provider attempts",
    empty: "No records",
    step: "Verify MFA for QA review and closure",
    system: "Automatic observation",
    details: "Evidence details",
    view: "View incident",
    commands: {
      acknowledge: "Acknowledge",
      investigate: "Record investigation",
      corrective_action: "Record corrective action",
      qa_review: "QA review",
      close: "QA close",
      amend: "Append amendment",
    },
    states: {
      open: "Open",
      acknowledged: "Acknowledged",
      investigating: "Investigating",
      awaiting_qa: "Awaiting QA",
      qa_reviewed: "QA reviewed",
      closed: "Closed",
    },
    kinds: {
      too_warm: "Too warm",
      too_cold: "Too cold",
      invalid_reading: "Invalid reading",
      sensor_no_data: "Sensor has no data",
      gateway_offline: "Gateway offline",
      rapid_change: "Rapid change",
    },
  },
  da: {
    title: "Hændelser og menneskelig respons",
    notice:
      "Kun syntetisk dokumentation. Genopretning lukker ikke en hændelse. QA-gennemgang og observeret genopretning kræves før lukning; lukning er ikke en fødevaresikkerhedserklæring.",
    all: "Alle tilstande",
    state: "Menneskelig responsstatus",
    kind: "Klassifikation",
    opened: "Åbnet",
    recovered: "Genopretning observeret",
    none: "Ikke registreret",
    assigned: "Tildelt",
    timeline: "Uforanderlig tidslinje",
    attachments: "Dokumentationsbilag",
    file: "UTF-8-tekstfil (højst 64 KiB)",
    label: "Bilagstitel",
    attach: "Vedhæft dokumentation",
    restriction:
      "Kun ren .txt-dokumentation er aktiveret. Aktive dokumenter, billeder og arkiver afvises.",
    action: "Responshandling",
    text: "Dokumentation, begrundelse eller SOP-reference",
    save: "Registrér handling",
    assignee: "Tildel ansvarlig",
    assign: "Tildel",
    export: "Download aktivitet som JSON",
    get: "Download",
    providers: "Udbyderforsøg",
    empty: "Ingen poster",
    step: "Bekræft MFA til QA-gennemgang og lukning",
    system: "Automatisk observation",
    details: "Dokumentationsdetaljer",
    view: "Se hændelse",
    commands: {
      acknowledge: "Kvittér",
      investigate: "Registrér undersøgelse",
      corrective_action: "Registrér korrigerende handling",
      qa_review: "QA-gennemgang",
      close: "QA-lukning",
      amend: "Tilføj rettelse",
    },
    states: {
      open: "Åben",
      acknowledged: "Kvitteret",
      investigating: "Undersøges",
      awaiting_qa: "Afventer QA",
      qa_reviewed: "QA-gennemgået",
      closed: "Lukket",
    },
    kinds: {
      too_warm: "For varmt",
      too_cold: "For koldt",
      invalid_reading: "Ugyldig måling",
      sensor_no_data: "Sensor uden data",
      gateway_offline: "Gateway offline",
      rapid_change: "Hurtig ændring",
    },
  },
};

/** Localize human status without conflating automatic recovery with closure. */
export function incidentState(state: string, locale: "en" | "da") {
  return labels[locale].states[state as keyof typeof labels.en.states] ?? state;
}

/** Show localized lifecycle meaning while the expanded evidence retains machine identifiers. */
export function incidentEventTitle(kind: string, locale: "en" | "da") {
  const t = labels[locale];
  const names: Record<string, string> = {
    "incident.opened.v1": t.states.open,
    "incident.recurred.v1": t.states.open,
    "incident.recovered.v1": t.recovered,
    "incident.acknowledged.v1": t.states.acknowledged,
    "incident.assigned.v1": t.assigned,
    "incident.investigated.v1": t.states.investigating,
    "incident.corrective_action.v1": t.commands.corrective_action,
    "incident.qa_reviewed.v1": t.states.qa_reviewed,
    "incident.resolved.v1": t.states.closed,
    "incident.amended.v1": t.commands.amend,
    "incident.evidence_attached.v1": t.attachments,
  };
  return names[kind] ?? kind;
}

/** Bind incident browsing and mutations to the common authenticated site selector. */
export function IncidentsPage() {
  const { locale } = useLocale();
  return (
    <>
      <h1>{labels[locale].title}</h1>
      <p role="note">{labels[locale].notice}</p>
      <ScopedWorkspace>
        {(scope) => <IncidentList key={scope.site.id} {...scope} />}
      </ScopedWorkspace>
    </>
  );
}

/** Apply visible filters only after obtaining the server-scoped collection. */
function IncidentList(scope: WorkspaceScope) {
  const { locale } = useLocale();
  const t = labels[locale];
  const identity = useIdentityMessages();
  const [state, setState] = useState("");
  const [kind, setKind] = useState("");
  const [selected, setSelected] = useState("");
  const query = useQuery({
    queryKey: ["incident-list", scope.base],
    queryFn: () => collection<Schema["Incident"]>(scope.base + "incidents/"),
    refetchInterval: 10000,
    retry: false,
  });
  const items = query.data?.filter(
    (item) =>
      (!state || item.status === state) && (!kind || item.kind === kind),
  );
  const item = items?.find((item) => item.id === selected) ?? items?.[0];
  if (query.isError) return <p role="alert">{identity.failed}</p>;
  return (
    <>
      <div className="admin-form">
        <label className="form-field">
          {t.state}
          <select value={state} onChange={(e) => setState(e.target.value)}>
            <option value="">{t.all}</option>
            {Object.entries(t.states).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="form-field">
          {t.kind}
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">{t.all}</option>
            {Object.entries(t.kinds).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {!query.data ? (
        <p role="status">{identity.loading}</p>
      ) : items?.length === 0 ? (
        <p>{t.empty}</p>
      ) : (
        <label className="form-field">
          {t.view}
          <select
            value={item?.id ?? ""}
            onChange={(e) => setSelected(e.target.value)}
          >
            {items?.map((incident) => (
              <option key={incident.id} value={incident.id}>
                {t.kinds[incident.kind]} ·{" "}
                {localTime(incident.opened_at, scope.site.timezone, locale)} ·{" "}
                {incidentState(incident.status, locale)}
              </option>
            ))}
          </select>
        </label>
      )}
      {item && <IncidentDetail key={item.id} {...scope} item={item} />}
    </>
  );
}

/** Keep response forms separate from evidence; changed revisions are revalidated by the API. */
function IncidentDetail({
  base,
  roles,
  site,
  item,
}: WorkspaceScope & { item: Schema["Incident"] }) {
  const { locale } = useLocale();
  const t = labels[locale];
  const identity = useIdentityMessages();
  const cache = useQueryClient();
  const prefix = base + `incidents/${item.id}/`;
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const responder = roles.some((role) =>
    ["owner", "site_admin", "qa", "operations", "operator"].includes(role),
  );
  const manager = roles.some((role) =>
    ["owner", "site_admin", "qa", "operations"].includes(role),
  );
  const exporter = manager || roles.includes("auditor");
  const query = useQuery({
    queryKey: ["incident-evidence", prefix],
    queryFn: async () => {
      const [events, files, notifications] = await Promise.all([
        collection<Schema["Event"]>(prefix + "events/"),
        collection<Schema["Attachment"]>(prefix + "attachments/"),
        collection<Schema["Notification"]>(prefix + "notifications/"),
      ]);
      return { events, files, notifications };
    },
    refetchInterval: 10000,
    retry: false,
  });
  const assignees = useQuery({
    queryKey: ["incident-assignees", prefix],
    enabled: manager,
    queryFn: () => collection<Schema["Candidate"]>(prefix + "assignees/"),
  });
  const actions: Array<keyof typeof t.commands> = ["amend"];
  if (item.status === "open") actions.unshift("acknowledge");
  if (["acknowledged", "investigating"].includes(item.status))
    actions.unshift("investigate");
  if (["investigating", "awaiting_qa", "qa_reviewed"].includes(item.status))
    actions.unshift("corrective_action");
  if (roles.includes("qa") && item.status === "awaiting_qa")
    actions.unshift("qa_review");
  if (
    roles.includes("qa") &&
    item.status === "qa_reviewed" &&
    item.recovered_at
  )
    actions.unshift("close");
  /** Fail visibly and refresh only this site's response/evidence after successful writes. */
  async function perform(task: () => Promise<unknown>) {
    setBusy(true);
    setError(false);
    try {
      await task();
      await Promise.all([
        cache.invalidateQueries({ queryKey: ["incident-list", base] }),
        cache.invalidateQueries({ queryKey: ["incident-evidence", prefix] }),
      ]);
      return true;
    } catch {
      setError(true);
      return false;
    } finally {
      setBusy(false);
    }
  }
  /** Submit an explicit human command with revision and replay token; text is never interpreted as code. */
  function submit(event: FormEvent<HTMLFormElement>, action?: string) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    void perform(() =>
      api(prefix + "commands/", "POST", {
        ...values,
        action: action ?? values.action,
        revision: item.revision,
        request_id: crypto.randomUUID(),
      }),
    ).then((ok) => {
      if (ok) form.reset();
    });
  }
  if (query.isError) return <p role="alert">{identity.failed}</p>;
  return (
    <>
      {error && <p role="alert">{identity.failed}</p>}
      <section className="workspace">
        <h2>{t.kinds[item.kind]}</h2>
        <p>
          {t.state}: {incidentState(item.status, locale)}
        </p>
        <p>
          {t.opened}: {localTime(item.opened_at, site.timezone, locale)}
        </p>
        <p>
          {t.recovered}:{" "}
          {item.recovered_at
            ? localTime(item.recovered_at, site.timezone, locale)
            : t.none}
        </p>
        <p>
          {t.assigned}: {item.assigned_label ?? t.none}
        </p>
        {responder && (
          <>
            <form className="admin-form" onSubmit={(e) => submit(e)}>
              <label className="form-field">
                {t.action}
                <select name="action">
                  {actions.map((action) => (
                    <option key={action} value={action}>
                      {t.commands[action]}
                    </option>
                  ))}
                </select>
              </label>
              <label className="form-field">
                {t.text}
                <textarea name="text" required minLength={8} maxLength={4000} />
              </label>
              <button disabled={busy}>{t.save}</button>
            </form>
            {roles.includes("qa") && <Link to="/security">{t.step}</Link>}
          </>
        )}
        {manager && item.status !== "closed" && (
          <form className="admin-form" onSubmit={(e) => submit(e, "assign")}>
            <label className="form-field">
              {t.assignee}
              <select name="assignee" required>
                {assignees.data?.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.email}
                  </option>
                ))}
              </select>
            </label>
            <Field name="text" label={t.text} />
            <button disabled={busy}>{t.assign}</button>
          </form>
        )}
        {exporter && (
          <button
            disabled={busy}
            onClick={() =>
              void perform(() =>
                download(prefix + "activity/", `incident-${item.id}.json`),
              )
            }
          >
            {t.export}
          </button>
        )}
      </section>
      <section className="workspace">
        <h2>{t.timeline}</h2>
        {query.data?.events.map((event) => (
          <article key={event.id}>
            <h3>{incidentEventTitle(event.kind, locale)}</h3>
            <p>
              {localTime(event.occurred_at, site.timezone, locale)} ·{" "}
              {evidenceText(event.evidence, "actor_email") ?? t.system}
            </p>
            {evidenceText(event.evidence, "text") && (
              <p>{evidenceText(event.evidence, "text")}</p>
            )}
            <details>
              <summary>{t.details}</summary>
              <pre className="evidence-json">
                {JSON.stringify(event.evidence, null, 2)}
              </pre>
            </details>
          </article>
        ))}
      </section>
      <section className="workspace">
        <h2>{t.attachments}</h2>
        <p>{t.restriction}</p>
        {responder && item.status !== "closed" && (
          <form
            className="admin-form"
            onSubmit={(e) => {
              e.preventDefault();
              const form = e.currentTarget;
              const body = new FormData(form);
              body.set("revision", String(item.revision));
              void perform(() => upload(prefix + "attachments/", body)).then(
                (ok) => {
                  if (ok) form.reset();
                },
              );
            }}
          >
            <Field name="label" label={t.label} />
            <label className="form-field">
              {t.file}
              <input
                type="file"
                name="file"
                accept=".txt,text/plain"
                required
              />
            </label>
            <button disabled={busy}>{t.attach}</button>
          </form>
        )}
        {query.data?.files.map((file) => (
          <p key={file.id}>
            {file.label} · {file.size} B{" "}
            <button
              disabled={busy}
              onClick={() =>
                void perform(() =>
                  download(
                    prefix + `attachments/${file.id}/download/`,
                    `evidence-${file.id}.txt`,
                  ),
                )
              }
            >
              {t.get}
            </button>
          </p>
        ))}
      </section>
      <section className="workspace">
        <h2>{t.providers}</h2>
        {query.data?.notifications.length === 0 && <p>{t.empty}</p>}
        {query.data?.notifications.map((notification) => (
          <p key={notification.id}>
            TEST · {notification.status} · {notification.attempts}
          </p>
        ))}
      </section>
    </>
  );
}
