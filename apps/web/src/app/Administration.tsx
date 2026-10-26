/** Scoped tenant administration. UI capabilities are hints; every command is reauthorized by DRF. */
import { useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  collection,
  type Organisation,
  type Site,
  type Member,
  type Invitation,
  type Audit,
} from "../api/identity";
import {
  Field,
  failureText,
  useIdentity,
  useIdentityMessages,
} from "./Identity";

type Section = "organisations" | "sites" | "users" | "audit";

/** Native form wrapper disables duplicate submission and reports localized request outcomes. */
function Command({
  children,
  label,
  execute,
}: {
  children: ReactNode;
  label: string;
  execute: (data: Record<string, FormDataEntryValue>) => Promise<void>;
}) {
  const t = useIdentityMessages();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  /** Await the authorized command so failed submissions retain input for correction. */
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      await execute(Object.fromEntries(new FormData(event.currentTarget)));
      setMessage(t.success);
    } catch (error) {
      setMessage(failureText(error, t));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="admin-form" onSubmit={submit}>
      {children}
      <button disabled={busy}>{busy ? t.loading : label}</button>
      {message && <p role="status">{message}</p>}
    </form>
  );
}

/** Load all bounded pages within one validated endpoint; no tenant data survives account changes. */
export function Administration({ section }: { section: Section }) {
  const { user, loading } = useIdentity();
  const t = useIdentityMessages();
  if (loading) return <p role="status">{t.loading}</p>;
  if (!user)
    return (
      <>
        <h1>
          {section === "users"
            ? t.inviteUser
            : t[section === "sites" ? "site" : section]}
        </h1>
        <p>{t.signInFirst}</p>
        <Link to="/login">{t.login}</Link>
      </>
    );
  return <ScopedAdministration key={user.id} section={section} />;
}

/** Keep organisation selection explicit and derive management visibility from exact active roles. */
function ScopedAdministration({ section }: { section: Section }) {
  const { user, refresh } = useIdentity();
  const t = useIdentityMessages();
  const cache = useQueryClient();
  const [selected, setSelected] = useState("");
  const orgs = useQuery({
    queryKey: ["admin", user?.id, "organisations"],
    queryFn: () => collection<Organisation>("/api/v1/organisations/"),
  });
  const org = orgs.data?.find((org) => org.id === selected) ?? orgs.data?.[0];
  const grants =
    user?.memberships.find((member) => member.organisation === org?.id)
      ?.roles ?? [];
  const owner = grants.some((grant) => grant.role === "owner");
  const manager = owner || grants.some((grant) => grant.role === "site_admin");
  const canReadAudit =
    owner ||
    grants.some((grant) =>
      ["site_admin", "qa", "auditor"].includes(grant.role),
    );
  const base = `/api/v1/organisations/${org?.id}/`;
  const scoped = !!org && grants.length > 0;
  const sites = useQuery({
    queryKey: ["admin", user?.id, org?.id, "sites"],
    queryFn: () => collection<Site>(base + "sites/"),
    enabled: scoped,
  });
  const members = useQuery({
    queryKey: ["admin", user?.id, org?.id, "members"],
    queryFn: () => collection<Member>(base + "members/"),
    enabled: scoped && manager && section === "users",
  });
  const invites = useQuery({
    queryKey: ["admin", user?.id, org?.id, "invitations"],
    queryFn: () => collection<Invitation>(base + "invitations/"),
    enabled: scoped && manager && section === "users",
  });
  const audit = useQuery({
    queryKey: ["admin", user?.id, org?.id, "audit"],
    queryFn: () => collection<Audit>(base + "audit/"),
    enabled: scoped && canReadAudit && section === "audit",
  });
  /** Refresh both data and capabilities after a write; revocations take effect immediately. */
  async function mutate(path: string, body?: unknown, method = "POST") {
    await api(path, method, body);
    await cache.invalidateQueries({ queryKey: ["admin"] });
    await refresh();
  }
  const editableSites =
    sites.data?.filter(
      (site) =>
        owner ||
        grants.some(
          (role) => role.role === "site_admin" && role.site === site.id,
        ),
    ) ?? [];
  const roles = owner
    ? ([
        "owner",
        "site_admin",
        "qa",
        "operations",
        "operator",
        "auditor",
      ] as const)
    : (["operations", "operator", "auditor"] as const);
  const scopeFields = (
    <>
      <label className="form-field">
        {t.role}
        <select name="role">
          {roles.map((role) => (
            <option key={role} value={role}>
              {t[role]}
            </option>
          ))}
        </select>
      </label>
      <label className="form-field">
        {t.site}
        <select name="site_id">
          {owner && <option value="">{t.wholeOrg}</option>}
          {editableSites.map((site) => (
            <option key={site.id} value={site.id}>
              {site.name}
            </option>
          ))}
        </select>
      </label>
    </>
  );
  if (orgs.isPending) return <p role="status">{t.loading}</p>;
  const failure = [orgs, sites, members, invites, audit].find(
    (query) => query.isError,
  );
  return (
    <>
      <h1>
        {section === "sites"
          ? t.site
          : section === "users"
            ? t.inviteUser
            : t[section]}
      </h1>
      {failure && <p role="alert">{failureText(failure.error, t)}</p>}
      <label className="form-field">
        {t.organisation}
        <select
          value={org?.id ?? ""}
          onChange={(event) => setSelected(event.target.value)}
        >
          <option value="" disabled>
            {t.select}
          </option>
          {orgs.data?.map((org) => (
            <option key={org.id} value={org.id}>
              {org.name}
            </option>
          ))}
        </select>
      </label>
      <p>
        <Link to="/security">{t.stepUp}</Link>
      </p>
      {!org && <p>{t.noData}</p>}
      {section === "organisations" && (
        <>
          {org && (
            <section className="workspace" key={org.id}>
              <h2>{org.name}</h2>
              <p>
                {org.country_code} · {org.timezone_default}
              </p>
              {owner && (
                <Command
                  label={t.save}
                  execute={(data) => mutate(base, data, "PATCH")}
                >
                  <Field name="name" label={t.name} value={org.name} />
                  <Field
                    name="country_code"
                    label={t.country}
                    value={org.country_code}
                  />
                  <Field
                    name="timezone_default"
                    label={t.timezone}
                    value={org.timezone_default}
                  />
                </Command>
              )}
            </section>
          )}
          {user?.platform_admin && (
            <section className="workspace">
              <h2>{t.provisioning}</h2>
              <Command
                label={t.create}
                execute={(data) => mutate("/api/v1/organisations/", data)}
              >
                <Field name="name" label={t.name} />
                <Field name="owner_email" label={t.ownerEmail} type="email" />
              </Command>
            </section>
          )}
        </>
      )}
      {section === "sites" && (
        <>
          {owner && (
            <section className="workspace">
              <h2>{t.create}</h2>
              <Command
                label={t.create}
                execute={(data) => mutate(base + "sites/", data)}
              >
                <Field name="name" label={t.name} />
                <Field
                  name="timezone"
                  label={t.timezone}
                  value={org?.timezone_default}
                />
              </Command>
            </section>
          )}
          {sites.isFetching && <p role="status">{t.loading}</p>}
          {!sites.data?.length && !sites.isFetching && <p>{t.noData}</p>}
          {sites.data?.map((site) => (
            <section className="workspace" key={site.id}>
              <h2>{site.name}</h2>
              <p>
                {t.planned} · {site.timezone}
                {site.archived && ` · ${t.archived}`}
              </p>
              {editableSites.some((item) => item.id === site.id) && (
                <>
                  <Command
                    label={t.save}
                    execute={(data) =>
                      mutate(base + `sites/${site.id}/`, data, "PATCH")
                    }
                  >
                    <Field name="name" label={t.name} value={site.name} />
                    <Field
                      name="timezone"
                      label={t.timezone}
                      value={site.timezone}
                    />
                  </Command>
                  <Command
                    label={site.archived ? t.restore : t.archive}
                    execute={() =>
                      mutate(
                        base + `sites/${site.id}/`,
                        { archived: !site.archived },
                        "PATCH",
                      )
                    }
                  >
                    {null}
                  </Command>
                </>
              )}
            </section>
          ))}
        </>
      )}
      {section === "users" && manager && (
        <>
          <section className="workspace">
            <h2>{t.inviteUser}</h2>
            <p>{t.localMail}</p>
            <Command
              label={t.inviteUser}
              execute={(data) =>
                mutate(base + "invitations/", {
                  ...data,
                  site_id: data.site_id || null,
                })
              }
            >
              <Field name="email" label={t.email} type="email" />
              {scopeFields}
            </Command>
          </section>
          <section className="workspace">
            <h2>{t.grant}</h2>
            <Command
              label={t.grant}
              execute={(data) =>
                mutate(base + "roles/", {
                  ...data,
                  site_id: data.site_id || null,
                })
              }
            >
              <label className="form-field">
                {t.member}
                <select name="membership_id" required>
                  {members.data
                    ?.filter((member) => member.active)
                    .map((member) => (
                      <option key={member.id} value={member.id}>
                        {member.email}
                      </option>
                    ))}
                </select>
              </label>
              {scopeFields}
            </Command>
          </section>
          {members.data?.map((member) => (
            <section className="workspace" key={member.id}>
              <h2>{member.email}</h2>
              <p>{member.active ? t.active : t.inactive}</p>
              {owner && (
                <Command
                  label={member.active ? t.deactivate : t.reactivate}
                  execute={() =>
                    mutate(
                      base + `members/${member.id}/`,
                      { active: !member.active },
                      "PATCH",
                    )
                  }
                >
                  {null}
                </Command>
              )}
              <ul>
                {member.roles.map((role) => (
                  <li key={role.id}>
                    {t[role.role]} ·{" "}
                    {sites.data?.find((site) => site.id === role.site)?.name ??
                      t.wholeOrg}
                    {(owner ||
                      !["owner", "site_admin", "qa"].includes(role.role)) && (
                      <Command
                        label={t.revoke}
                        execute={() =>
                          mutate(base + `roles/${role.id}/revoke/`)
                        }
                      >
                        {null}
                      </Command>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          ))}
          {invites.data?.map((invite) => (
            <section className="workspace" key={invite.id}>
              <h2>{invite.email}</h2>
              <p>
                {t[invite.role]} ·{" "}
                {new Date(invite.expires_at).toLocaleString()}
              </p>
              {!invite.accepted_at && !invite.revoked_at && (
                <Command
                  label={t.revoke}
                  execute={() =>
                    mutate(base + `invitations/${invite.id}/revoke/`)
                  }
                >
                  {null}
                </Command>
              )}
            </section>
          ))}
        </>
      )}
      {section === "audit" && canReadAudit && (
        <section className="workspace">
          <h2>{t.audit}</h2>
          {audit.isFetching && <p>{t.loading}</p>}
          {!audit.data?.length && <p>{t.noData}</p>}
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t.when}</th>
                  <th>{t.action}</th>
                  <th>{t.subject}</th>
                  <th>{t.hash}</th>
                </tr>
              </thead>
              <tbody>
                {audit.data?.map((event) => (
                  <tr key={event.id}>
                    <td>
                      {new Date(event.occurred_at).toLocaleString(undefined, {
                        timeZone: org?.timezone_default,
                      })}
                    </td>
                    <td>{event.action}</td>
                    <td>{event.subject}</td>
                    <td>
                      <code>{event.event_hash}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
