/** Owner/platform commercial metadata; no checkout, collection or monitoring suspension. */
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "../../../../packages/api-contracts/schema";
import {
  api,
  collection,
  download,
  type Me,
  type Organisation,
} from "../api/identity";
import { useLocale } from "../i18n/LocaleProvider";
import { useIdentity, useIdentityMessages } from "./Identity";
import { localTime } from "./Monitoring";

type Plan = components["schemas"]["Plan"];

/** Avoid all commercial queries for anonymous users and site-only roles. */
export function BillingPage() {
  const { user, loading } = useIdentity();
  const { locale } = useLocale();
  const t = useIdentityMessages();
  if (loading) return <p role="status">{t.loading}</p>;
  if (!user) return <Link to="/login">{t.signInFirst}</Link>;
  if (
    !user.platform_admin &&
    !user.memberships.some((member) =>
      member.roles.some((role) => role.role === "owner"),
    )
  )
    return (
      <p role="alert">
        {locale === "da"
          ? "Kun organisationsejere og kommercielle administratorer kan se fakturering."
          : "Only organisation owners and commercial administrators can view billing."}
      </p>
    );
  return <BillingSelection key={user.id} user={user} />;
}

/** Select only current owned metadata; a site grant never implies organisation-wide billing access. */
function BillingSelection({ user }: { user: Me }) {
  const t = useIdentityMessages();
  const [selected, setSelected] = useState("");
  const orgs = useQuery({
    queryKey: ["billing-organisations", user.id],
    queryFn: () => collection<Organisation>("/api/v1/organisations/"),
  });
  const plans = useQuery({
    queryKey: ["plans", user.id],
    queryFn: () => collection<Plan>("/api/v1/plans/"),
  });
  const ownerIds = user.memberships
    .filter((member) => member.roles.some((role) => role.role === "owner"))
    .map((member) => member.organisation);
  const permitted = orgs.data?.filter(
    (org) => user.platform_admin || ownerIds.includes(org.id),
  );
  const org = permitted?.find((row) => row.id === selected) ?? permitted?.[0];
  if (orgs.isError || plans.isError) return <p role="alert">{t.failed}</p>;
  if (!orgs.data || !plans.data) return <p role="status">{t.loading}</p>;
  return (
    <>
      <label className="form-field">
        {t.organisation}
        <select
          value={org?.id ?? ""}
          onChange={(event) => setSelected(event.target.value)}
        >
          {permitted?.map((row) => (
            <option key={row.id} value={row.id}>
              {row.name}
            </option>
          ))}
        </select>
      </label>
      {org && (
        <BillingEditor
          key={org.id}
          org={org}
          plans={plans.data}
          platform={user.platform_admin}
          owner={ownerIds.includes(org.id)}
        />
      )}
    </>
  );
}

/** Bind every form, export and cache entry to the selected organisation; failures hide stale metadata. */
function BillingEditor({
  org,
  plans,
  platform,
  owner,
}: {
  org: Organisation;
  plans: Plan[];
  platform: boolean;
  owner: boolean;
}) {
  const { locale } = useLocale();
  const t = useIdentityMessages();
  const da = locale === "da";
  const base = `/api/v1/organisations/${org.id}/`;
  const cache = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const subscription = useQuery({
    queryKey: ["subscription", org.id],
    queryFn: () =>
      api<components["schemas"]["SubscriptionStatus"]>(base + "subscription/"),
  });
  const invoices = useQuery({
    queryKey: ["invoices", org.id],
    queryFn: () =>
      collection<components["schemas"]["Invoice"]>(base + "invoices/"),
  });
  const history = useQuery({
    queryKey: ["subscription-history", org.id],
    queryFn: () =>
      collection<components["schemas"]["TermsChange"]>(
        base + "subscription/history/",
      ),
  });
  /** Translate the owned local catalog; unknown future templates retain their supplied name. */
  function planName(plan: Plan) {
    const names: Record<string, string> = {
      "local-trial-v1": "Lokal prøveskabelon",
      "local-pilot-v1": "Lokal pilotskabelon",
      "local-demo-v1": "Lokal demoskabelon",
    };
    return da ? (names[plan.code] ?? plan.name) : plan.name;
  }
  const states: Record<string, string> = da
    ? {
        trial: "Prøve",
        pilot: "Pilot",
        active: "Aktiv",
        past_due: "Afventer afklaring",
        ending: "Udløber",
        ended: "Afsluttet",
      }
    : {
        trial: "Trial",
        pilot: "Pilot",
        active: "Active",
        past_due: "Review overdue",
        ending: "Ending",
        ended: "Ended",
      };
  /** Refresh authoritative status/history only after the selected bounded action completes. */
  async function perform(work: () => Promise<unknown>) {
    setBusy(true);
    setError(false);
    try {
      await work();
      await cache.invalidateQueries({ queryKey: ["subscription", org.id] });
      await cache.invalidateQueries({ queryKey: ["invoices", org.id] });
      await cache.invalidateQueries({
        queryKey: ["subscription-history", org.id],
      });
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }
  /** Preserve owner-controlled contacts; plan/state escalation fields never enter this payload. */
  function settings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void perform(() =>
      api(base + "subscription/", "PATCH", {
        billing_name: data.get("billing_name"),
        billing_email: data.get("billing_email"),
        purchase_reference: data.get("purchase_reference"),
      }),
    );
  }
  /** Only the explicit platform commercial form can request reviewed local term changes. */
  function terms(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void perform(() =>
      api(base + "subscription/", "POST", {
        plan: data.get("plan"),
        state: data.get("state"),
        ends_at: data.get("ends_at") || null,
        reason: data.get("reason"),
      }),
    );
  }
  /** Record nominal entered amounts; no provider, VAT rate or exchange-rate calculation is implied. */
  function draft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void perform(() =>
      api(base + "invoices/", "POST", Object.fromEntries(data)),
    );
  }
  if (subscription.isError || invoices.isError || history.isError)
    return <p role="alert">{t.failed}</p>;
  if (!subscription.data || !invoices.data || !history.data)
    return <p role="status">{t.loading}</p>;
  const sub = subscription.data;
  return (
    <>
      <h1>{da ? "Plan, forbrug og fakturering" : "Plan, usage and billing"}</h1>
      <p className="notice">
        {da
          ? "Lokal, syntetisk konfiguration. Kun manuelle finanskladder; ingen betaling opkræves."
          : "Local synthetic configuration. Manual finance drafts only; no payment is collected."}
      </p>
      <p>
        {da ? "Kommerciel status" : "Commercial state"}:{" "}
        {states[sub.warnings.includes("term_ended") ? "ended" : sub.state]}
      </p>
      <p>
        {da ? "Lokationer" : "Sites"}: {sub.usage.sites} / {sub.limits.sites} ·{" "}
        {da ? "Sensorer" : "Sensors"}: {sub.usage.sensors} /{" "}
        {sub.limits.sensors} · {da ? "Pr. lokation" : "Per site"}:{" "}
        {sub.limits.sensors_per_site}
      </p>
      {!sub.expansion_allowed && (
        <p role="status">
          {da
            ? "Udvidelse er blokeret. Eksisterende dataindsamling og hændelsesbehandling fortsætter."
            : "Expansion is blocked. Existing ingestion and incident response continue."}
        </p>
      )}
      {sub.warnings.length > 0 && (
        <p role="status">
          {da
            ? "Planens løbetid eller kapacitet kræver gennemgang."
            : "Plan term or capacity needs review."}{" "}
          {sub.ends_at}
        </p>
      )}
      <h2>{da ? "Serverens planskabeloner" : "Server plan templates"}</h2>
      <ul>
        {plans.map((plan) => (
          <li key={plan.code}>
            {planName(plan)} — {plan.max_sites} {da ? "lokationer" : "sites"},{" "}
            {plan.max_sensors} {da ? "sensorer" : "sensors"},{" "}
            {plan.max_sensors_per_site}/{da ? "lokation" : "site"}
            {sub.plan === plan.code ? (da ? " · valgt" : " · selected") : ""}
          </li>
        ))}
      </ul>
      <p>
        <Link to="/security">
          {da
            ? "Bekræft MFA igen før ændringer"
            : "Confirm recent MFA before changes"}
        </Link>
      </p>
      {error && <p role="alert">{t.failed}</p>}
      {owner && (
        <form className="admin-form" onSubmit={settings}>
          <h2>{da ? "Faktureringskontakt" : "Billing contact"}</h2>
          <label className="form-field">
            {da ? "Virksomhedsnavn" : "Company name"}
            <input
              name="billing_name"
              maxLength={160}
              defaultValue={sub.billing_name}
            />
          </label>
          <label className="form-field">
            {da ? "E-mail" : "Email"}
            <input
              type="email"
              name="billing_email"
              defaultValue={sub.billing_email}
            />
          </label>
          <label className="form-field">
            {da ? "Indkøbsreference" : "Purchase reference"}
            <input
              name="purchase_reference"
              maxLength={80}
              defaultValue={sub.purchase_reference}
            />
          </label>
          <button disabled={busy}>{da ? "Gem kontakt" : "Save contact"}</button>
        </form>
      )}
      {platform && (
        <>
          <form className="admin-form" onSubmit={terms}>
            <h2>
              {da ? "Kommerciel administration" : "Commercial administration"}
            </h2>
            <label className="form-field">
              {da ? "Plan" : "Plan"}
              <select name="plan" defaultValue={sub.plan}>
                {plans.map((plan) => (
                  <option key={plan.code} value={plan.code}>
                    {planName(plan)}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-field">
              {da ? "Status" : "State"}
              <select name="state" defaultValue={sub.state}>
                {Object.entries(states).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-field">
              {da
                ? "Udløb med tidszone, tomt uden udløb"
                : "End with timezone offset, blank for no end"}
              <input
                name="ends_at"
                defaultValue={sub.ends_at ?? ""}
                placeholder="2026-11-20T12:00:00+01:00"
              />
            </label>
            <label className="form-field">
              {da ? "Begrundelse" : "Reason"}
              <textarea name="reason" required minLength={8} maxLength={500} />
            </label>
            <button disabled={busy}>
              {da ? "Gem lokale vilkår" : "Save local terms"}
            </button>
          </form>
          <form className="admin-form" onSubmit={draft}>
            <h2>{da ? "Manuel finanskladde" : "Manual finance draft"}</h2>
            <label className="form-field">
              {da ? "Unik reference" : "Unique reference"}
              <input
                name="reference"
                required
                maxLength={40}
                pattern="[A-Z][A-Z0-9-]{1,39}"
              />
            </label>
            <label className="form-field">
              {da ? "Periodestart" : "Period start"}
              <input name="period_start" type="date" required />
            </label>
            <label className="form-field">
              {da ? "Periodeslut" : "Period end"}
              <input name="period_end" type="date" required />
            </label>
            <label className="form-field">
              {da ? "Valuta" : "Currency"}
              <select name="currency">
                <option>DKK</option>
                <option>EUR</option>
                <option>USD</option>
              </select>
            </label>
            <label className="form-field">
              {da ? "Nettobeløb" : "Net amount"}
              <input
                name="net_amount"
                type="number"
                min="0"
                step="0.01"
                required
              />
            </label>
            <label className="form-field">
              {da
                ? "Afgiftsbeløb, indtastet af økonomi"
                : "Tax amount, entered by finance"}
              <input
                name="tax_amount"
                type="number"
                min="0"
                step="0.01"
                required
              />
            </label>
            <button disabled={busy}>
              {da ? "Registrér kladde" : "Record draft"}
            </button>
          </form>
        </>
      )}
      <details>
        <summary>
          {da ? "Bevaret vilkårshistorik" : "Preserved term history"}
        </summary>
        <ul>
          {history.data.map((row) => (
            <li key={row.id}>
              {localTime(
                row.recorded_at,
                org.timezone_default ?? "UTC",
                locale,
              )}{" "}
              · {row.reason}
              <pre className="evidence-json">
                {JSON.stringify(
                  {
                    before: row.before,
                    after: row.after,
                    actor: row.recorded_by,
                  },
                  null,
                  2,
                )}
              </pre>
            </li>
          ))}
        </ul>
      </details>
      <h2>{da ? "Bevarede finanskladder" : "Preserved finance drafts"}</h2>
      {invoices.data.length === 0 ? (
        <p>{da ? "Ingen kladder registreret." : "No drafts recorded."}</p>
      ) : (
        <ul>
          {invoices.data.map((row) => (
            <li key={row.id}>
              {row.reference} · {row.currency} {row.net_amount} +{" "}
              {row.tax_amount}{" "}
              <button
                disabled={busy}
                onClick={() =>
                  void perform(() =>
                    download(
                      base + `invoices/${row.id}/export/`,
                      "invoice-draft.csv",
                    ),
                  )
                }
              >
                {da ? "Eksportér kladde" : "Export draft"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
