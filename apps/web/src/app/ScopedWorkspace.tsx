/** Shared authenticated site selector. Granted API results, never local claims, determine scope. */
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { collection, type Organisation, type Site } from "../api/identity";
import { useIdentity, useIdentityMessages } from "./Identity";

/** Scope provided to domain screens; roles control presentation while the server enforces access. */
export type WorkspaceScope = { site: Site; base: string; roles: string[] };

/** Remount all domain state when identity/site changes; anonymous users issue no tenant requests. */
export function ScopedWorkspace({
  children,
}: {
  children: (scope: WorkspaceScope) => ReactNode;
}) {
  const { user, loading } = useIdentity();
  const t = useIdentityMessages();
  if (loading) return <p role="status">{t.loading}</p>;
  if (!user) return <Link to="/login">{t.signInFirst}</Link>;
  return <Selection key={user.id}>{children}</Selection>;
}

/** Resolve organisations/sites independently; query failures hide cached privileged screens. */
function Selection({
  children,
}: {
  children: (scope: WorkspaceScope) => ReactNode;
}) {
  const { user } = useIdentity();
  const t = useIdentityMessages();
  const [orgId, setOrg] = useState("");
  const [siteId, setSite] = useState("");
  const orgs = useQuery({
    queryKey: ["workspace-orgs", user?.id],
    queryFn: () => collection<Organisation>("/api/v1/organisations/"),
  });
  const org = orgs.data?.find((item) => item.id === orgId) ?? orgs.data?.[0];
  const sites = useQuery({
    queryKey: ["workspace-sites", user?.id, org?.id],
    enabled: !!org,
    queryFn: () => collection<Site>(`/api/v1/organisations/${org?.id}/sites/`),
  });
  const site =
    sites.data?.find((item) => item.id === siteId) ?? sites.data?.[0];
  const roles =
    user?.memberships
      .find((item) => item.organisation === org?.id)
      ?.roles.filter((role) => role.role === "owner" || role.site === site?.id)
      .map((role) => role.role) ?? [];
  if (orgs.isError || sites.isError) return <p role="alert">{t.failed}</p>;
  return (
    <>
      <div className="admin-form">
        <label className="form-field">
          {t.organisation}
          <select
            value={org?.id ?? ""}
            onChange={(e) => {
              setOrg(e.target.value);
              setSite("");
            }}
          >
            {orgs.data?.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label className="form-field">
          {t.site}
          <select
            value={site?.id ?? ""}
            onChange={(e) => setSite(e.target.value)}
          >
            {sites.data?.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {site && (
        <section key={site.id}>
          {children({
            site,
            base: `/api/v1/organisations/${site.organisation}/sites/${site.id}/`,
            roles,
          })}
        </section>
      )}
    </>
  );
}
