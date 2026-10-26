/** Scoped help, internal support and immutable onboarding references; no external dispatch. */
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "../../../../packages/api-contracts/schema";
import { api, collection } from "../api/identity";
import { useLocale } from "../i18n/LocaleProvider";
import { useIdentityMessages } from "./Identity";
import { ScopedWorkspace, type WorkspaceScope } from "./ScopedWorkspace";
import { localTime } from "./Monitoring";

type Ticket = components["schemas"]["Ticket"];

/** Session/site remounts discard draft text and selected request IDs across scope changes. */
export function HelpPage() {
  return (
    <ScopedWorkspace>
      {(scope) => <HelpWorkspace scope={scope} />}
    </ScopedWorkspace>
  );
}

/** Current site diagnostics, customer-local ticket queue and owner support approvals. */
function HelpWorkspace({ scope }: { scope: WorkspaceScope }) {
  const { locale } = useLocale();
  const t = useIdentityMessages();
  const da = locale === "da";
  const cache = useQueryClient();
  const [selected, setSelected] = useState("");
  const [requestId, setRequestId] = useState(() => crypto.randomUUID());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const owner = scope.roles.includes("owner");
  const mayWrite = scope.roles.some((role) =>
    ["owner", "site_admin", "qa", "operations", "operator"].includes(role),
  );
  const mayExport = scope.roles.some((role) =>
    ["owner", "site_admin", "qa", "operations", "auditor"].includes(role),
  );
  const status = useQuery({
    queryKey: ["operations", scope.base],
    queryFn: () =>
      api<components["schemas"]["OperationalStatus"]>(
        scope.base + "operational-status/",
      ),
    refetchInterval: 15000,
  });
  const requests = useQuery({
    queryKey: ["tickets", scope.base],
    queryFn: () => collection<Ticket>(scope.base + "support-tickets/"),
  });
  const archive = useQuery({
    queryKey: ["archive", scope.base],
    enabled: mayExport,
    queryFn: () =>
      api<components["schemas"]["ArtifactArchive"]>(
        scope.base + "artifact-archive/",
      ),
  });
  const sessions = useQuery({
    queryKey: ["support-sessions", scope.base],
    enabled: owner,
    queryFn: () =>
      collection<components["schemas"]["Session"]>(
        scope.base + "support-sessions/",
      ),
  });
  const accesses = useQuery({
    queryKey: ["support-access", scope.base],
    enabled: owner,
    queryFn: () =>
      collection<components["schemas"]["Access"]>(
        scope.base + "support-access/",
      ),
  });
  const ticket = requests.data?.find((row) => row.id === selected);
  const steps: Record<string, string> = da
    ? {
        scope_and_responsibilities:
          "Aftal skrivebeskyttet omfang, ansvar og beredskab.",
        placement_and_calibration:
          "Dokumentér placering, referenceinstrument og kalibrering.",
        qa_rules_and_cadence:
          "QA gennemgår grænser, varighed, datarytme og SOP.",
        routes_and_failure_drills:
          "Afprøv TEST-ruter, udfald, genafspilning og eskalation.",
        human_response_training:
          "Træn kvittering, undersøgelse, korrigerende handling og QA-lukning.",
        reviewed_acceptance_archive:
          "Bevar acceptreferencer; syntetiske beviser godkender ikke et anlæg.",
      }
    : {
        scope_and_responsibilities:
          "Agree read-only scope, responsibilities and contingency.",
        placement_and_calibration:
          "Record placement, reference instrument and calibration.",
        qa_rules_and_cadence:
          "QA reviews thresholds, durations, cadence and SOP.",
        routes_and_failure_drills:
          "Exercise TEST routes, outages, replay and escalation.",
        human_response_training:
          "Train acknowledgement, investigation, corrective action and QA closure.",
        reviewed_acceptance_archive:
          "Preserve acceptance references; synthetic evidence does not approve a site.",
      };
  const gates: Record<string, string> = da
    ? {
        authorised_hardware_site_missing: "Godkendt udstyr og anlæg mangler",
        container_security_remediation:
          "Containerfund skal afhjælpes og vurderes",
        external_security_legal_privacy_review:
          "Ekstern sikkerheds-, juridisk og privatlivsgennemgang",
        cloud_paging_backup_and_site_drills:
          "Cloudalarmer, backup og anlægsøvelser",
        customer_qa_training_acceptance: "Kundens QA, træning og accept",
        finance_support_terms_review: "Økonomi- og supportvilkår",
        unresolved_incidents: "Uafsluttede hændelser kræver gennemgang",
        failed_delivery_or_processing:
          "Leverings- eller behandlingsfejl kræver gennemgang",
      }
    : {
        authorised_hardware_site_missing:
          "Authorised hardware and site missing",
        container_security_remediation:
          "Container findings require remediation/review",
        external_security_legal_privacy_review:
          "External security, legal and privacy review",
        cloud_paging_backup_and_site_drills:
          "Cloud paging, backup and site drills",
        customer_qa_training_acceptance: "Customer QA, training and acceptance",
        finance_support_terms_review: "Finance and support terms",
        unresolved_incidents: "Unresolved incidents require review",
        failed_delivery_or_processing:
          "Delivery or processing failures require review",
      };
  /** Refresh scope-bound sources after success; a failed response never implies a request was delivered. */
  async function perform(work: () => Promise<unknown>) {
    setBusy(true);
    setError(false);
    try {
      await work();
      await cache.invalidateQueries({ queryKey: ["tickets", scope.base] });
      await cache.invalidateQueries({
        queryKey: ["support-sessions", scope.base],
      });
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }
  /** Keep the replay ID on errors; reset only after confirmed creation. No mail/provider is invoked. */
  function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    void perform(async () => {
      const created = await api<Ticket>(
        scope.base + "support-tickets/",
        "POST",
        {
          request_id: requestId,
          subject: data.get("subject"),
          body: data.get("body"),
        },
      );
      setSelected(created.id);
      setRequestId(crypto.randomUUID());
      form.reset();
    });
  }
  /** Approval is exact-site diagnostics only; recent MFA and independent staff identity are server checks. */
  function approve(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void perform(() =>
      api(scope.base + "support-sessions/", "POST", {
        supporter: data.get("supporter"),
        minutes: Number(data.get("minutes")),
        reason: data.get("reason"),
      }),
    );
  }
  if (
    status.isError ||
    requests.isError ||
    (mayExport && archive.isError) ||
    (owner && (sessions.isError || accesses.isError))
  )
    return <p role="alert">{t.failed}</p>;
  if (!status.data || !requests.data) return <p role="status">{t.loading}</p>;
  return (
    <>
      <h1>
        {da
          ? "Hjælp, onboarding og driftsstatus"
          : "Help, onboarding and operational status"}
      </h1>
      <p className="notice">
        {da
          ? "Produktion er blokeret. Der er ingen godkendt fysisk pilot eller automatisk idriftsættelse."
          : "Production is blocked. There is no approved physical pilot or automatic go-live."}
      </p>
      <p>
        {da
          ? "Datafejl eller manglende alarmer er ikke bevis for fødevaresikkerhed. Brug teamets aftalte beredskab og egenkontrol."
          : "Data failures or absent alarms are not proof of food safety. Use the team's agreed contingency and own-check procedures."}
      </p>
      <p>
        {da ? "Sensorer" : "Sensors"}: {status.data.site_status.sensors} ·{" "}
        {da ? "Åbne hændelser" : "Unresolved incidents"}:{" "}
        {status.data.site_status.unresolved_incidents} ·{" "}
        {da ? "Leveringsfejl" : "Delivery issues"}:{" "}
        {status.data.site_status.failed_notifications}
      </p>
      <details>
        <summary>
          {da
            ? "Aktuelt diagnostisk øjebliksbillede"
            : "Current diagnostic snapshot"}
        </summary>
        <pre className="evidence-json">
          {JSON.stringify(status.data.site_status.operational, null, 2)}
        </pre>
      </details>
      <h2>{da ? "Onboarding og træning" : "Onboarding and training"}</h2>
      <ol>
        {status.data.onboarding_steps.map((step) => (
          <li key={step}>{steps[step] ?? step}</li>
        ))}
      </ol>
      <p>
        <Link to="/sensors">
          {da ? "Idriftsættelsespakke" : "Commissioning pack"}
        </Link>{" "}
        · <Link to="/rules">{da ? "QA-regler" : "QA rules"}</Link> ·{" "}
        <Link to="/notifications">{da ? "TEST-ruter" : "TEST routes"}</Link> ·{" "}
        <Link to="/incidents">
          {da ? "Hændelsesrespons" : "Incident response"}
        </Link>
      </p>
      <h2>{da ? "Afventende frigivelseskrav" : "Outstanding release gates"}</h2>
      <ul>
        {status.data.blockers.map((gate) => (
          <li key={gate}>{gates[gate] ?? gate}</li>
        ))}
      </ul>
      {mayExport && (
        <details>
          <summary>
            {da
              ? "Bevarede accept- og rapportreferencer"
              : "Preserved acceptance and report references"}
          </summary>
          <p>
            {da
              ? "Seneste 50 pr. type; oprindelige kilder og adgangskrav bevares."
              : "Latest 50 per type; original sources and download permissions are preserved."}
          </p>
          <pre className="evidence-json">
            {JSON.stringify(archive.data, null, 2)}
          </pre>
          <Link to="/reports">
            {da
              ? "Rapportbygger og godkendte downloads"
              : "Report builder and authorised downloads"}
          </Link>
        </details>
      )}
      <h2>{da ? "Interne supportanmodninger" : "Internal support requests"}</h2>
      <p>
        {da
          ? "Anmodninger bevares i teamets arbejdsområde. Intet sendes til en ekstern leverandør. Undlad adgangskoder, betalingskort og uvedkommende persondata."
          : "Requests stay in the team's workspace. Nothing is sent to an external supplier. Keep passwords, payment cards and unrelated personal data out."}
      </p>
      {error && <p role="alert">{t.failed}</p>}
      {mayWrite && (
        <form className="admin-form" onSubmit={create}>
          <label className="form-field">
            {da ? "Emne" : "Subject"}
            <input name="subject" required minLength={3} maxLength={160} />
          </label>
          <label className="form-field">
            {da ? "Beskrivelse" : "Description"}
            <textarea name="body" required minLength={8} maxLength={2000} />
          </label>
          <button disabled={busy}>
            {da ? "Opret supportanmodning" : "Create support request"}
          </button>
        </form>
      )}
      {requests.data.length === 0 ? (
        <p>{da ? "Ingen synlige anmodninger." : "No visible requests."}</p>
      ) : (
        <ul className="support-message">
          {requests.data.map((row) => (
            <li key={row.id}>
              <button onClick={() => setSelected(row.id)}>{row.subject}</button>{" "}
              ·{" "}
              {row.status === "resolved"
                ? da
                  ? "Afsluttet"
                  : "Resolved"
                : row.status === "in_progress"
                  ? da
                    ? "Under behandling"
                    : "In progress"
                  : da
                    ? "Åben"
                    : "Open"}
            </li>
          ))}
        </ul>
      )}
      {ticket && (
        <TicketConversation
          key={`${ticket.id}:${ticket.revision}`}
          ticket={ticket}
          scope={scope}
          mayWrite={mayWrite}
        />
      )}
      {owner && (
        <section>
          <h2>
            {da
              ? "Godkendt SAMSEL-supportadgang"
              : "Approved SAMSEL support access"}
          </h2>
          <p>
            {da
              ? "Kun diagnostiske antal for denne lokation, højst 60 minutter. Ingen rå målinger, filer eller medlemsrettigheder."
              : "Diagnostic counts for this site only, up to 60 minutes. No raw readings, files or membership privileges."}
          </p>
          <Link to="/security">
            {da
              ? "Bekræft MFA før godkendelse eller tilbagekaldelse"
              : "Confirm MFA before approval or revocation"}
          </Link>
          <form className="admin-form" onSubmit={approve}>
            <label className="form-field">
              {da
                ? "Supportmedarbejderens oplyste konto-ID"
                : "Support staff's provided account ID"}
              <input
                name="supporter"
                required
                pattern="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
              />
            </label>
            <label className="form-field">
              {da ? "Minutter" : "Minutes"}
              <input name="minutes" type="number" min={1} max={60} required />
            </label>
            <label className="form-field">
              {da ? "Formål" : "Purpose"}
              <textarea name="reason" minLength={8} maxLength={500} required />
            </label>
            <button disabled={busy}>
              {da ? "Godkend diagnostisk adgang" : "Approve diagnostic access"}
            </button>
          </form>
          <ul>
            {sessions.data?.map((session) => (
              <li key={session.id}>
                {session.reason} ·{" "}
                {localTime(session.expires_at, scope.site.timezone, locale)}{" "}
                {session.revoked_at ? (
                  da ? (
                    "Tilbagekaldt"
                  ) : (
                    "Revoked"
                  )
                ) : (
                  <button
                    disabled={busy}
                    onClick={() =>
                      void perform(() =>
                        api(
                          scope.base + `support-sessions/${session.id}/revoke/`,
                          "POST",
                        ),
                      )
                    }
                  >
                    {da ? "Tilbagekald" : "Revoke"}
                  </button>
                )}
              </li>
            ))}
          </ul>
          <h3>{da ? "Bevaret adgangslog" : "Preserved access log"}</h3>
          <ul>
            {accesses.data?.map((access) => (
              <li key={access.id}>
                {localTime(access.accessed_at, scope.site.timezone, locale)} ·{" "}
                {access.action}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

/** Render plain escaped conversation text; replies cannot amend original evidence or close incidents. */
function TicketConversation({
  ticket,
  scope,
  mayWrite,
}: {
  ticket: Ticket;
  scope: WorkspaceScope;
  mayWrite: boolean;
}) {
  const { locale } = useLocale();
  const da = locale === "da";
  const t = useIdentityMessages();
  const cache = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const path = scope.base + `support-tickets/${ticket.id}/events/`;
  const events = useQuery({
    queryKey: ["ticket-events", scope.base, ticket.id],
    queryFn: () => collection<components["schemas"]["TicketEvent"]>(path),
  });
  /** Use the server revision; conflicting/lost replies fail and require a fresh conversation view. */
  async function reply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError(false);
    try {
      await api(path, "POST", {
        revision: ticket.revision,
        message: data.get("message"),
        status: data.get("status"),
      });
      await cache.invalidateQueries({
        queryKey: ["ticket-events", scope.base, ticket.id],
      });
      await cache.invalidateQueries({ queryKey: ["tickets", scope.base] });
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }
  if (events.isError) return <p role="alert">{t.failed}</p>;
  return (
    <section>
      <h3 className="support-message">{ticket.subject}</h3>
      <p>
        {da
          ? "Supportstatus ændrer ikke en sikkerhedshændelse."
          : "Support state does not change a safety incident."}
      </p>
      <ol>
        {events.data?.map((event) => (
          <li key={event.id}>
            <time>
              {localTime(event.created_at, scope.site.timezone, locale)}
            </time>
            <p className="support-message">{event.message}</p>
          </li>
        ))}
      </ol>
      {mayWrite && (
        <form className="admin-form" onSubmit={(event) => void reply(event)}>
          <label className="form-field">
            {da ? "Svar" : "Reply"}
            <textarea name="message" required minLength={3} maxLength={2000} />
          </label>
          <label className="form-field">
            {da ? "Supportstatus" : "Support state"}
            <select name="status" defaultValue={ticket.status}>
              <option value="open">{da ? "Åben" : "Open"}</option>
              <option value="in_progress">
                {da ? "Under behandling" : "In progress"}
              </option>
              <option value="resolved">{da ? "Afsluttet" : "Resolved"}</option>
            </select>
          </label>
          <button disabled={busy}>{da ? "Gem svar" : "Save reply"}</button>
        </form>
      )}
      {error && <p role="alert">{t.failed}</p>}
    </section>
  );
}
