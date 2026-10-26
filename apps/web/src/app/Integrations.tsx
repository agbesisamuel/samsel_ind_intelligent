/** Scoped software adapter preparation and immutable synthetic pilot reviews. */
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "../../../../packages/api-contracts/schema";
import { api, collection } from "../api/identity";
import { useLocale } from "../i18n/LocaleProvider";
import { useIdentityMessages } from "./Identity";
import { ScopedWorkspace, type WorkspaceScope } from "./ScopedWorkspace";
import { localTime } from "./Monitoring";

/** A synthetic review can never change this message into a hardware-compatibility claim. */
export function pilotBoundary(locale: "en" | "da") {
  return locale === "da"
    ? "BLOKERET: intet godkendt udstyr eller anlæg"
    : "BLOCKED: no authorised hardware/site";
}

/** Reuse the current-grant selector; remount pending review text whenever site/session changes. */
export function IntegrationsPage() {
  return (
    <ScopedWorkspace>
      {(scope) => <Preparation scope={scope} />}
    </ScopedWorkspace>
  );
}

/** Fail visibly on query errors; the server derives all counts and enforces review authority. */
function Preparation({ scope }: { scope: WorkspaceScope }) {
  const { locale } = useLocale();
  const t = useIdentityMessages();
  const da = locale === "da";
  const cache = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const status = useQuery({
    queryKey: ["adapter", scope.base],
    queryFn: () =>
      api<components["schemas"]["AdapterStatus"]>(
        scope.base + "adapter-readiness/",
      ),
  });
  const reviews = useQuery({
    queryKey: ["pilot-reviews", scope.base],
    queryFn: () =>
      collection<components["schemas"]["PilotReview"]>(
        scope.base + "pilot-reviews/",
      ),
  });
  const mayReview = scope.roles.some((role) =>
    ["owner", "site_admin", "qa", "operations", "operator"].includes(role),
  );
  /** Append the entered observation; successful writes clear the form and refresh scoped history. */
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    setBusy(true);
    setError(false);
    try {
      await api(scope.base + "pilot-reviews/", "POST", {
        kind: values.get("kind"),
        note: values.get("note"),
      });
      form.reset();
      await cache.invalidateQueries({
        queryKey: ["pilot-reviews", scope.base],
      });
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }
  if (status.isError || reviews.isError) return <p role="alert">{t.failed}</p>;
  if (!status.data || !reviews.data) return <p role="status">{t.loading}</p>;
  return (
    <>
      <h1>
        {da
          ? "Integration og pilotforberedelse"
          : "Integration and pilot preparation"}
      </h1>
      <p role="status" className="notice">
        {pilotBoundary(locale)}
      </p>
      <p>
        {da
          ? "Kun softwareprofilen sii-simulator-v1 er tilgængelig. Den læser ingen fysisk enhed. Syntetiske gennemgange giver ikke tilladelse til idriftsættelse."
          : "Only software profile sii-simulator-v1 is available. It reads no physical equipment. Synthetic reviews do not authorise go-live."}
      </p>
      <p>
        {da ? "Sensorer" : "Sensors"}: {status.data.sensors} ·{" "}
        {da ? "Åbne hændelser" : "Unresolved incidents"}:{" "}
        {status.data.unresolved_incidents} ·{" "}
        {da ? "Leveringsfejl" : "Delivery issues"}:{" "}
        {status.data.failed_notifications}
      </p>
      <p>
        <Link to="/sensors">
          {da
            ? "Placering, kalibrering og idriftsættelsespakke"
            : "Placement, calibration and commissioning pack"}
        </Link>{" "}
        ·{" "}
        <Link to="/notifications">
          {da ? "Kontrollér TEST-ruter" : "Review TEST routes"}
        </Link>
      </p>
      {mayReview && (
        <form className="admin-form" onSubmit={(event) => void submit(event)}>
          <h2>
            {da ? "Registrér syntetisk gennemgang" : "Record synthetic review"}
          </h2>
          <p>
            <Link to="/security">
              {da
                ? "Ny MFA-bekræftelse er påkrævet"
                : "Recent MFA confirmation required"}
            </Link>
          </p>
          <label className="form-field">
            {da ? "Gennemgang" : "Review"}
            <select name="kind">
              <option value="daily_health">
                {da ? "Dagligt sundhedstjek" : "Daily health review"}
              </option>
              <option value="weekly_feedback">
                {da ? "Ugentlig feedback" : "Weekly feedback"}
              </option>
            </select>
          </label>
          <label className="form-field">
            {da
              ? "Observation, ansvarlig opfølgning og begrænsninger"
              : "Observation, responsible follow-up and limitations"}
            <textarea name="note" required minLength={8} maxLength={1000} />
          </label>
          <button disabled={busy}>
            {da ? "Gem gennemgang" : "Save review"}
          </button>
          {error && <p role="alert">{t.failed}</p>}
        </form>
      )}
      <h2>{da ? "Bevaret gennemgangshistorik" : "Preserved review history"}</h2>
      {reviews.data.length === 0 ? (
        <p>{da ? "Ingen gennemgange registreret." : "No reviews recorded."}</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>{da ? "Tidspunkt" : "Time"}</th>
              <th>{da ? "Type" : "Type"}</th>
              <th>{da ? "Observation" : "Observation"}</th>
            </tr>
          </thead>
          <tbody>
            {reviews.data.map((review) => (
              <tr key={review.id}>
                <td>
                  {localTime(review.recorded_at, scope.site.timezone, locale)}
                </td>
                <td>
                  {review.kind === "daily_health"
                    ? da
                      ? "Daglig"
                      : "Daily"
                    : da
                      ? "Ugentlig"
                      : "Weekly"}
                </td>
                <td>{review.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
