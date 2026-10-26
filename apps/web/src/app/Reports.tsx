/** Bounded asynchronous evidence exports; current server grants control every download. */
import { useState, type FormEvent, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "../../../../packages/api-contracts/schema";
import { api, collection, download } from "../api/identity";
import { useLocale } from "../i18n/LocaleProvider";
import { useIdentityMessages } from "./Identity";
import { ScopedWorkspace, type WorkspaceScope } from "./ScopedWorkspace";
import { localTime } from "./Monitoring";

/** Native wrapped labels keep text/select controls accessible without generated identifier state. */
function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="form-field">
      {label}
      {children}
    </label>
  );
}

/** Session/site remount prevents a pending export form from crossing tenant selection. */
export function ReportsPage() {
  return (
    <ScopedWorkspace>{(scope) => <Reports scope={scope} />}</ScopedWorkspace>
  );
}

/** Only export-capable roles issue report queries; operators see a clear restriction. */
function Reports({ scope }: { scope: WorkspaceScope }) {
  const { locale } = useLocale();
  const permitted = scope.roles.some((r) =>
    ["owner", "site_admin", "qa", "operations", "auditor"].includes(r),
  );
  if (!permitted)
    return (
      <p role="alert">
        {locale === "da"
          ? "Din rolle tillader ikke eksport."
          : "Your role does not permit exports."}
      </p>
    );
  return <Builder scope={scope} />;
}

/** Poll bounded job metadata; failures hide cached ready states and never fabricate completion. */
function Builder({ scope }: { scope: WorkspaceScope }) {
  const { locale } = useLocale();
  const t = useIdentityMessages();
  const da = locale === "da";
  const query = useQueryClient();
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const jobs = useQuery({
    queryKey: ["reports", scope.base],
    refetchInterval: 5000,
    queryFn: () =>
      collection<components["schemas"]["Report"]>(scope.base + "reports/"),
  });
  const zones = useQuery({
    queryKey: ["report-zones", scope.base],
    queryFn: () =>
      collection<components["schemas"]["Zone"]>(scope.base + "zones/"),
  });
  /** Keep controls disabled during mutation; report expiry and grant consumption are server decisions. */
  async function perform(work: () => Promise<unknown>) {
    setBusy(true);
    setError(false);
    try {
      await work();
      await query.invalidateQueries({ queryKey: ["reports", scope.base] });
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }
  /** Submit explicit-offset timestamps; the server rejects ambiguous DST/local times and large windows. */
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    void perform(() =>
      api(scope.base + "reports/", "POST", {
        start: form.get("start"),
        end: form.get("end"),
        format: form.get("format"),
        locale,
        ...(form.get("zone") ? { zone: form.get("zone") } : {}),
      }),
    );
  }
  const states: Record<string, string> = da
    ? {
        queued: "I kø",
        running: "Genereres",
        ready: "Klar",
        failed: "Mislykket",
      }
    : {
        queued: "Queued",
        running: "Generating",
        ready: "Ready",
        failed: "Failed",
      };
  return (
    <>
      <h1>{da ? "Evidensrapporter" : "Evidence reports"}</h1>
      <p>
        {da
          ? "Syntetiske data. Rå data, dækning, huller og kvalifikation bevares. Ingen vurdering af fødevaresikkerhed. Maks. 31 dage og 10.000 poster; større forespørgsler afvises. Filer udløber efter 24 timer."
          : "Synthetic data. Raw data, coverage, gaps and qualification are preserved. No food-safety verdict. Maximum 31 days and 10,000 records; larger requests are rejected. Files expire after 24 hours."}
      </p>
      {(error || jobs.isError || zones.isError) && (
        <p role="alert">{t.failed}</p>
      )}
      <form className="admin-form" onSubmit={submit}>
        <Field label={da ? "Fra (med UTC-offset)" : "From (with UTC offset)"}>
          <input
            name="start"
            required
            placeholder="2026-10-20T00:00:00+02:00"
          />
        </Field>
        <Field
          label={
            da
              ? "Til, eksklusiv (med UTC-offset)"
              : "Until, exclusive (with UTC offset)"
          }
        >
          <input name="end" required placeholder="2026-10-21T00:00:00+02:00" />
        </Field>
        <Field label="Zone">
          <select name="zone">
            <option value="">{da ? "Hele stedet" : "Entire site"}</option>
            {!zones.isError &&
              zones.data?.map((z) => (
                <option key={z.id} value={z.id}>
                  {z.name}
                </option>
              ))}
          </select>
        </Field>
        <Field label="Format">
          <select name="format">
            <option value="pdf">PDF</option>
            <option value="csv">CSV</option>
          </select>
        </Field>
        <button disabled={busy}>
          {da ? "Opret rapport" : "Create report"}
        </button>
      </form>
      {!jobs.isError && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>{da ? "Bestilt" : "Requested"}</th>
                <th>Status</th>
                <th>Format</th>
                <th>{da ? "Udløber" : "Expires"}</th>
                <th>{da ? "Handling" : "Action"}</th>
              </tr>
            </thead>
            <tbody>
              {jobs.data?.map((job) => (
                <tr key={job.id}>
                  <td>
                    {localTime(job.requested_at, scope.site.timezone, locale)}
                  </td>
                  <td>
                    {states[job.status] ?? job.status}
                    {job.error_code && <p>{job.error_code}</p>}
                  </td>
                  <td>{job.format}</td>
                  <td>
                    {localTime(job.expires_at, scope.site.timezone, locale)}
                  </td>
                  <td>
                    {job.status === "failed" && job.attempts < 3 && (
                      <button
                        disabled={busy}
                        onClick={() =>
                          void perform(() =>
                            api(
                              scope.base + `reports/${job.id}/retry/`,
                              "POST",
                            ),
                          )
                        }
                      >
                        {da ? "Prøv igen" : "Retry"}
                      </button>
                    )}
                    {job.status === "ready" && (
                      <button
                        disabled={busy}
                        onClick={() =>
                          void perform(async () => {
                            const grant = await api<
                              components["schemas"]["Grant"]
                            >(scope.base + `reports/${job.id}/access/`, "POST");
                            await download(
                              scope.base +
                                `reports/${job.id}/downloads/${grant.id}/`,
                              `report-${job.id}.${job.format}`,
                            );
                          })
                        }
                      >
                        {da ? "Hent" : "Download"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
