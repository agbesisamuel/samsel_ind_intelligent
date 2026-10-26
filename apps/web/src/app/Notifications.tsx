/** Verified TEST routes and durable delivery health; acceptance never means human acknowledgement. */
import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import type { components } from "../../../../packages/api-contracts/schema";
import { api, collection } from "../api/identity";
import { useLocale } from "../i18n/LocaleProvider";
import { Field, useIdentity, useIdentityMessages } from "./Identity";
import { ScopedWorkspace, type WorkspaceScope } from "./ScopedWorkspace";

type Schema = components["schemas"];
const messages = {
  en: {
    title: "Notifications",
    notice:
      "TEST delivery to local capture only. Provider acceptance is not human acknowledgement. Missing delivery requires attention.",
    health: "Delivery health",
    worker: "Worker",
    pending: "Pending",
    dead: "Dead or uncertain",
    issues: "Open delivery issues",
    accepted: "Provider accepted",
    contacts: "Recipient opt-in",
    invite: "Request email proof",
    user: "Granted account",
    contact: "Recipient",
    proof: "Email proof",
    confirm: "Confirm my opt-in",
    disable: "Disable",
    verified: "Verified",
    unverified: "Unverified",
    disabled: "Disabled",
    routes: "Routes",
    name: "Route name",
    contingency: "Contingency recipient",
    secondary: "Escalation recipient",
    delay: "Escalation delay (seconds)",
    none: "None",
    zone: "Timezone",
    start: "Shift start (minutes since midnight)",
    end: "Shift end (1440 means midnight)",
    kinds: "Classifications (comma-separated)",
    severity: "Severity",
    create: "Create route",
    test: "Send TEST",
    enable: "Enable",
    queue: "Delivery evidence",
    step: "Verify MFA",
    empty: "No records",
    attempts: "Attempts",
    status: "Provider state",
    running: "Running",
    unknown: "Unknown or delayed",
    info: "Information",
    warning: "Warning",
    critical: "Critical",
    allDay:
      "For all-day coverage enter 0 and 1440. Overnight shifts are supported. Create separate routes for additional contacts.",
  },
  da: {
    title: "Notifikationer",
    notice:
      "TEST-levering kun til lokal opsamling. Udbyderaccept er ikke menneskelig kvittering. Manglende levering kræver opmærksomhed.",
    health: "Leveringsstatus",
    worker: "Arbejder",
    pending: "Afventer",
    dead: "Stoppet eller usikker",
    issues: "Åbne leveringsproblemer",
    accepted: "Accepteret af udbyder",
    contacts: "Modtagersamtykke",
    invite: "Anmod om e-mailbevis",
    user: "Konto med adgang",
    contact: "Modtager",
    proof: "E-mailbevis",
    confirm: "Bekræft mit samtykke",
    disable: "Deaktivér",
    verified: "Bekræftet",
    unverified: "Ikke bekræftet",
    disabled: "Deaktiveret",
    routes: "Ruter",
    name: "Rutenavn",
    contingency: "Reservemodtager",
    secondary: "Eskaleringsmodtager",
    delay: "Eskaleringsforsinkelse (sekunder)",
    none: "Ingen",
    zone: "Tidszone",
    start: "Vagtstart (minutter efter midnat)",
    end: "Vagtslut (1440 betyder midnat)",
    kinds: "Klassifikationer (kommasepareret)",
    severity: "Alvorlighed",
    create: "Opret rute",
    test: "Send TEST",
    enable: "Aktivér",
    queue: "Leveringsdokumentation",
    step: "Bekræft MFA",
    empty: "Ingen poster",
    attempts: "Forsøg",
    status: "Udbyderstatus",
    running: "Kører",
    unknown: "Ukendt eller forsinket",
    info: "Information",
    warning: "Advarsel",
    critical: "Kritisk",
    allDay:
      "For hele døgnet: indtast 0 og 1440. Nattevagter understøttes. Opret separate ruter til flere kontakter.",
  },
};

/** Unknown or expired worker heartbeats must never be presented as healthy. */
export function notificationHealth(value: string, locale: "en" | "da") {
  return value === "running"
    ? messages[locale].running
    : messages[locale].unknown;
}

/** Require authenticated exact-site grants before requesting notification data. */
export function NotificationsPage() {
  const { locale } = useLocale();
  return (
    <>
      <h1>{messages[locale].title}</h1>
      <p role="note">{messages[locale].notice}</p>
      <ScopedWorkspace>
        {(scope) => <NotificationWorkspace key={scope.site.id} {...scope} />}
      </ScopedWorkspace>
    </>
  );
}

/** Keep consent proofs in native form fields; never persist them or place them in query caches. */
function NotificationWorkspace({ base, roles, site }: WorkspaceScope) {
  const { locale } = useLocale();
  const t = messages[locale];
  const identity = useIdentityMessages();
  const { user } = useIdentity();
  const cache = useQueryClient();
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const manager = roles.some((role) => ["owner", "site_admin"].includes(role));
  const candidates = useQuery({
    queryKey: ["alert-candidates", base],
    enabled: manager,
    queryFn: () => collection<Schema["Candidate"]>(base + "alert-candidates/"),
  });
  const query = useQuery({
    queryKey: ["notification-workspace", base],
    queryFn: async () => {
      const [contacts, routes, queue, health] = await Promise.all([
        collection<Schema["Contact"]>(base + "alert-contacts/"),
        collection<Schema["Route"]>(base + "alert-routes/"),
        collection<Schema["Notification"]>(base + "notifications/"),
        api<Schema["Health"]>(base + "notification-health/"),
      ]);
      return { contacts, routes, queue, health };
    },
    refetchInterval: 10000,
    retry: false,
  });
  /** Reauthorize every command server-side; refresh only the selected site's evidence. */
  async function command(path: string, body?: unknown) {
    setBusy(true);
    setError(false);
    try {
      await api(base + path, "POST", body);
      await cache.invalidateQueries({
        queryKey: ["notification-workspace", base],
      });
      return true;
    } catch {
      setError(true);
      return false;
    } finally {
      setBusy(false);
    }
  }
  /** Read named fields synchronously without storing proof material in React state. */
  function fields(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    return Object.fromEntries(new FormData(event.currentTarget));
  }
  if (query.isError) return <p role="alert">{identity.failed}</p>;
  if (!query.data) return <p role="status">{identity.loading}</p>;
  const data = query.data;
  const verified = data.contacts.filter(
    (contact) => contact.verified_at && !contact.disabled,
  );
  /** Offer verified local choices; the dispatcher rechecks consent and grants before sending. */
  function choices() {
    return verified.map((contact) => (
      <option key={contact.id} value={contact.id}>
        {contact.email}
      </option>
    ));
  }
  return (
    <>
      {error && <p role="alert">{identity.failed}</p>}
      <section className="workspace">
        <h2>{t.health}</h2>
        <p>
          {t.worker}: {notificationHealth(data.health.worker, locale)}
        </p>
        <p>
          {t.pending}: {data.health.pending} · {t.dead}: {data.health.dead} ·{" "}
          {t.issues}: {data.health.issues} · {t.accepted}:{" "}
          {data.health.accepted}
        </p>
      </section>
      {manager && (
        <p>
          <Link to="/security">{t.step}</Link>
        </p>
      )}
      <section className="workspace">
        <h2>{t.contacts}</h2>
        {manager && (
          <form
            className="admin-form"
            onSubmit={(e) => void command("alert-contacts/", fields(e))}
          >
            <label className="form-field">
              {t.user}
              <select name="user" required>
                {candidates.data?.map((candidate) => (
                  <option key={candidate.id} value={candidate.id}>
                    {candidate.email}
                  </option>
                ))}
              </select>
            </label>
            <button disabled={busy}>{t.invite}</button>
          </form>
        )}
        {data.contacts.length === 0 && <p>{t.empty}</p>}
        {data.contacts.map((contact) => (
          <article key={contact.id}>
            <p>
              {contact.email} ·{" "}
              {contact.disabled
                ? t.disabled
                : contact.verified_at
                  ? t.verified
                  : t.unverified}
            </p>
            {contact.user === user?.id &&
              !contact.verified_at &&
              !contact.disabled && (
                <form
                  className="admin-form"
                  onSubmit={async (e) => {
                    const form = e.currentTarget;
                    if (
                      await command(
                        `alert-contacts/${contact.id}/confirm/`,
                        fields(e),
                      )
                    )
                      form.reset();
                  }}
                >
                  <Field name="token" label={t.proof} type="password" />
                  <button disabled={busy}>{t.confirm}</button>
                </form>
              )}
            {(manager || contact.user === user?.id) && !contact.disabled && (
              <button
                disabled={busy}
                onClick={() =>
                  void command(`alert-contacts/${contact.id}/disable/`)
                }
              >
                {t.disable}
              </button>
            )}
          </article>
        ))}
      </section>
      <section className="workspace">
        <h2>{t.routes}</h2>
        {manager && (
          <>
            <p>{t.allDay}</p>
            <form
              className="admin-form"
              onSubmit={(e) => {
                const values = fields(e);
                const body: Record<string, unknown> = {
                  ...values,
                  kinds: String(values.kinds)
                    .split(",")
                    .map((value) => value.trim()),
                  contingency: values.contingency || null,
                };
                if (!values.escalation_contact) {
                  delete body.escalation_contact;
                  delete body.delay_sec;
                }
                void command("alert-routes/", body);
              }}
            >
              <Field name="name" label={t.name} />
              <label className="form-field">
                {t.contact}
                <select name="contact" required>
                  {choices()}
                </select>
              </label>
              <label className="form-field">
                {t.contingency}
                <select name="contingency">
                  <option value="">{t.none}</option>
                  {choices()}
                </select>
              </label>
              <label className="form-field">
                {t.secondary}
                <select name="escalation_contact">
                  <option value="">{t.none}</option>
                  {choices()}
                </select>
              </label>
              <Field
                name="delay_sec"
                label={t.delay}
                type="number"
                required={false}
              />
              <Field name="timezone" label={t.zone} value={site.timezone} />
              <Field name="shift_start" label={t.start} type="number" />
              <Field name="shift_end" label={t.end} type="number" />
              <Field name="kinds" label={t.kinds} />
              <p>
                too_warm, too_cold, invalid_reading, sensor_no_data,
                gateway_offline
              </p>
              <label className="form-field">
                {t.severity}
                <select name="severity">
                  <option value="info">{t.info}</option>
                  <option value="warning">{t.warning}</option>
                  <option value="critical">{t.critical}</option>
                </select>
              </label>
              <button disabled={busy}>{t.create}</button>
            </form>
          </>
        )}
        {data.routes.map((route) => (
          <article key={route.id}>
            <h3>{route.name}</h3>
            <p>
              {route.severity} · {route.timezone} · {route.shift_start}–
              {route.shift_end} · {route.kinds.join(", ")}
            </p>
            {manager && (
              <>
                <button
                  disabled={busy || !route.enabled}
                  onClick={() => void command(`alert-routes/${route.id}/test/`)}
                >
                  {t.test}
                </button>
                <button
                  disabled={busy}
                  onClick={() =>
                    void command(`alert-routes/${route.id}/enabled/`, {
                      enabled: !route.enabled,
                    })
                  }
                >
                  {route.enabled ? t.disable : t.enable}
                </button>
              </>
            )}
          </article>
        ))}
      </section>
      <section className="workspace">
        <h2>{t.queue}</h2>
        {data.queue.length === 0 && <p>{t.empty}</p>}
        {data.queue.map((item) => (
          <article key={item.id}>
            <h3>
              TEST ·{" "}
              {data.routes.find((route) => route.id === item.route)?.name}
            </h3>
            <p>
              {t.status}: {item.status} · {t.attempts}: {item.attempts} ·{" "}
              {item.due_at}
            </p>
            <details>
              <summary>{t.attempts}</summary>
              <pre className="evidence-json">
                {JSON.stringify(item.history, null, 2)}
              </pre>
            </details>
          </article>
        ))}
      </section>
    </>
  );
}
