/** Exact-site inventory and preserved commissioning evidence, with explicit synthetic warnings. */
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import type { components } from "../../../../packages/api-contracts/schema";
import { api, collection, type Organisation, type Site } from "../api/identity";
import { useLocale } from "../i18n/LocaleProvider";
import { failureText, useIdentity, useIdentityMessages } from "./Identity";
import { inventoryMessages } from "./inventoryMessages";

type Schemas = components["schemas"];
type InventoryRecord =
  | Schemas["Building"]
  | Schemas["Zone"]
  | Schemas["Gateway"]
  | Schemas["Sensor"]
  | Schemas["Calibration"]
  | Schemas["SensorCommissioning"]
  | Schemas["SiteCommissioning"]
  | Schemas["CommissioningTest"]
  | Schemas["Acceptance"];
type Resource =
  | "buildings"
  | "zones"
  | "gateways"
  | "sensors"
  | "calibrations"
  | "sensor-commissionings"
  | "commissioning"
  | "commissioning-tests"
  | "acceptances";
type Copy = typeof inventoryMessages.en;
type FieldSpec = {
  name: keyof Copy;
  kind?: "number" | "datetime-local" | "checkbox";
  options?: string[];
  source?: Resource;
  optional?: boolean;
};
const fields: Record<Resource, FieldSpec[]> = {
  buildings: [{ name: "name" }],
  zones: [
    { name: "building", source: "buildings" },
    { name: "name" },
    { name: "zone_type" },
    { name: "sop_reference", optional: true },
    { name: "criticality", options: ["unreviewed", "standard", "critical"] },
  ],
  gateways: [
    { name: "name" },
    { name: "external_id" },
    { name: "firmware_version", optional: true },
  ],
  sensors: [
    { name: "zone", source: "zones" },
    { name: "gateway", source: "gateways" },
    { name: "name" },
    { name: "external_id" },
    { name: "sensor_type", options: ["temperature"] },
    { name: "unit", options: ["degC"] },
    { name: "expected_interval_sec", kind: "number" },
  ],
  calibrations: [
    { name: "sensor", source: "sensors" },
    { name: "reference" },
    { name: "checked_at", kind: "datetime-local" },
    { name: "due_at", kind: "datetime-local" },
  ],
  "sensor-commissionings": [
    { name: "sensor", source: "sensors" },
    { name: "technician_reference" },
    { name: "placement_reference" },
    { name: "read_only_scope", kind: "checkbox" },
  ],
  commissioning: [
    { name: "responsible_person" },
    { name: "customer_approval_reference", optional: true },
    { name: "contingency_reference", optional: true },
    { name: "read_only_scope", kind: "checkbox" },
  ],
  "commissioning-tests": [
    { name: "commissioning", source: "commissioning" },
    { name: "kind", options: ["sensor_feed", "breach", "no_data", "routing"] },
    { name: "passed", kind: "checkbox" },
    { name: "evidence_reference" },
  ],
  acceptances: [],
};
const resources = Object.keys(fields) as Resource[];
type Inventory = Record<Resource, InventoryRecord[]>;

/** Read one optional schema field without treating arbitrary JSON as renderable React content. */
function value(record: InventoryRecord, field: string): string {
  const result = (record as unknown as Record<string, unknown>)[field];
  return typeof result === "string"
    ? result
    : typeof result === "number"
      ? String(result)
      : "";
}

/** Display names/references plus short identity to distinguish multiple evidence versions. */
function label(record: InventoryRecord) {
  return (
    value(record, "name") ||
    `${value(record, "reference") || value(record, "responsible_person") || value(record, "kind")} · ${record.id.slice(0, 8)}`
  );
}

/** Guard the screen before any tenant fetch; selectors contain only server-permitted records. */
export function InventoryPage() {
  const { user, loading } = useIdentity();
  const t = useIdentityMessages();
  if (loading) return <p role="status">{t.loading}</p>;
  if (!user)
    return (
      <>
        <p>{t.signInFirst}</p>
        <Link to="/login">{t.login}</Link>
      </>
    );
  return <InventorySelection key={user.id} />;
}

/** Reset site contents when scope changes; no user-selected ID is taken as authorization. */
function InventorySelection() {
  const { user } = useIdentity();
  const t = useIdentityMessages();
  const i = inventoryMessages[useLocale().locale];
  const [orgId, setOrg] = useState("");
  const [siteId, setSite] = useState("");
  const orgs = useQuery({
    queryKey: ["inventory-orgs", user?.id],
    queryFn: () => collection<Organisation>("/api/v1/organisations/"),
  });
  const org = orgs.data?.find((org) => org.id === orgId) ?? orgs.data?.[0];
  const membership = user?.memberships.find(
    (member) => member.organisation === org?.id,
  );
  const sites = useQuery({
    queryKey: ["inventory-sites", user?.id, org?.id],
    queryFn: () => collection<Site>(`/api/v1/organisations/${org?.id}/sites/`),
    enabled: !!membership?.roles.length,
  });
  const site =
    sites.data?.find((site) => site.id === siteId) ?? sites.data?.[0];
  return (
    <>
      <h1>{i.title}</h1>
      <p>{i.noReadings}</p>
      {(orgs.isError || sites.isError) && <p role="alert">{t.failed}</p>}
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
            {orgs.data?.map((org) => (
              <option key={org.id} value={org.id}>
                {org.name}
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
            {sites.data?.map((site) => (
              <option key={site.id} value={site.id}>
                {site.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {site && org && (
        <InventoryWorkspace key={site.id} site={site} org={org} />
      )}
      {!site && <p>{t.noData}</p>}
    </>
  );
}

/** Render one site tree and validated native forms, preserving evidence as successive versions. */
function InventoryWorkspace({ org, site }: { org: Organisation; site: Site }) {
  const { user } = useIdentity();
  const t = useIdentityMessages();
  const { locale } = useLocale();
  const i = inventoryMessages[locale];
  const [resource, setResource] = useState<Resource>("sensors");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const base = `/api/v1/organisations/${org.id}/sites/${site.id}/`;
  const grants =
    user?.memberships.find((member) => member.organisation === org.id)?.roles ??
    [];
  const manager = grants.some(
    (role) =>
      role.role === "owner" ||
      (role.role === "site_admin" && role.site === site.id),
  );
  const qa = grants.some((role) => role.role === "qa" && role.site === site.id);
  const query = useQuery({
    queryKey: ["inventory", user?.id, org.id, site.id],
    queryFn: async () =>
      Object.fromEntries(
        await Promise.all(
          resources.map(async (key) => [
            key,
            await collection<InventoryRecord>(base + key + "/"),
          ]),
        ),
      ) as Inventory,
  });
  const gates = useQuery({
    queryKey: ["activation", user?.id, org.id, site.id],
    queryFn: () => api<{ blockers: string[] }>(base + "activation/"),
  });
  const canCreate =
    resource === "calibrations" ? qa : resource !== "acceptances" && manager;

  /** Localize known server warning codes; unexpected codes retain a non-green generic warning. */
  function translate(code: string) {
    return i[code as keyof Copy] ?? i.missing;
  }

  /** Re-read evidence and gates after a successful write; errors never fabricate completion. */
  async function command(path: string, body?: unknown, method = "POST") {
    setBusy(true);
    setMessage("");
    try {
      await api(path, method, body);
      await Promise.all([query.refetch(), gates.refetch()]);
      setMessage(t.success);
    } catch (error) {
      setMessage(failureText(error, t));
    } finally {
      setBusy(false);
    }
  }

  /** Normalize native form values to explicit JSON booleans/numbers/UTC dates before submission. */
  function submit(
    event: FormEvent<HTMLFormElement>,
    specs: FieldSpec[],
    path: string,
    method = "POST",
  ) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const payload = Object.fromEntries(
      specs.map((field) => {
        const raw = String(data.get(field.name) ?? "");
        return [
          field.name,
          field.kind === "checkbox"
            ? data.has(field.name)
            : field.kind === "number"
              ? Number(raw)
              : field.kind === "datetime-local"
                ? new Date(raw).toISOString()
                : raw,
        ];
      }),
    );
    void command(path, payload, method);
  }

  /** Use explicit labels and current scoped options; preserve immutable related IDs on edit. */
  function renderFields(specs: FieldSpec[], record?: InventoryRecord) {
    return specs.map((field) => (
      <label key={field.name} className="form-field">
        {i[field.name]}
        {field.source || field.options ? (
          <select
            name={field.name}
            required={!field.optional}
            defaultValue={record && value(record, field.name)}
          >
            {field.source
              ? query.data?.[field.source].map((item) => (
                  <option key={item.id} value={item.id}>
                    {label(item)}
                  </option>
                ))
              : field.options?.map((option) => (
                  <option key={option} value={option}>
                    {i[option as keyof Copy] ?? option}
                  </option>
                ))}
          </select>
        ) : (
          <input
            name={field.name}
            type={field.kind ?? "text"}
            required={!field.optional && field.kind !== "checkbox"}
            defaultValue={record && value(record, field.name)}
            min={field.kind === "number" ? 1 : undefined}
            max={field.kind === "number" ? 86400 : undefined}
            maxLength={240}
          />
        )}
      </label>
    ));
  }
  if (query.isPending) return <p role="status">{t.loading}</p>;
  if (query.isError) return <p role="alert">{t.failed}</p>;
  const evidence = [
    "calibrations",
    "sensor-commissionings",
    "commissioning",
    "commissioning-tests",
    "acceptances",
  ].includes(resource);
  return (
    <>
      <section className="notice">
        <h2>{i.blocked}</h2>
        {gates.isError && <p role="alert">{t.failed}</p>}
        <ul>
          {gates.data?.blockers.map((code) => (
            <li key={code}>{translate(code)}</li>
          ))}
        </ul>
        {manager && (
          <button
            disabled={busy}
            onClick={() => void command(base + "activation/")}
          >
            {i.activate}
          </button>
        )}
      </section>
      <nav className="inventory-tabs" aria-label={i.title}>
        {resources.map((key) => (
          <button
            key={key}
            aria-current={key === resource ? "page" : undefined}
            onClick={() => {
              setResource(key);
              setMessage("");
            }}
          >
            {i[key]}
          </button>
        ))}
      </nav>
      <h2>{i[resource]}</h2>
      <p>{evidence ? i.draft : i.noThreshold}</p>
      <p>
        <Link to="/security">{t.stepUp}</Link>
      </p>
      {message && <p role="status">{message}</p>}
      {canCreate && (
        <section className="workspace">
          <h3>{t.create}</h3>
          {resource === "calibrations" && <p>{i.dateHelp}</p>}
          <form
            key={resource}
            className="admin-form"
            onSubmit={(event) =>
              submit(event, fields[resource], base + resource + "/")
            }
          >
            {renderFields(fields[resource])}
            <button disabled={busy}>{t.create}</button>
          </form>
        </section>
      )}
      {!query.data[resource].length && <p>{t.noData}</p>}
      {query.data[resource].map((record) => {
        const qualification =
          "qualification" in record ? record.qualification : undefined;
        const editFields = fields[resource].filter(
          (field) => !field.source && field.name !== "external_id",
        );
        return (
          <section className="workspace" key={record.id}>
            <h3>{label(record)}</h3>
            {"synthetic" in record && record.synthetic && (
              <p className="badge">{i.synthetic}</p>
            )}
            {"state" in record && (
              <p>
                {record.state === "commissioning"
                  ? i.commissioningState
                  : translate(record.state)}
              </p>
            )}
            {"zone" in record && (
              <p>
                {i.zone}:{" "}
                {value(
                  query.data.zones.find((zone) => zone.id === record.zone) ??
                    record,
                  "name",
                )}{" "}
                · {i.gateway}:{" "}
                {label(
                  query.data.gateways.find(
                    (gateway) => gateway.id === record.gateway,
                  ) ?? record,
                )}
              </p>
            )}
            {qualification && (
              <>
                <p>{translate(qualification.calibration_status)}</p>
                <ul>
                  {qualification.warnings.map((warning) => (
                    <li key={warning}>{translate(warning)}</li>
                  ))}
                </ul>
              </>
            )}
            {"warnings" in record && (
              <ul>
                {record.warnings.map((warning) => (
                  <li key={warning}>{translate(warning)}</li>
                ))}
              </ul>
            )}
            {fields[resource]
              .filter((field) => field.name !== "name")
              .map((field) => (
                <p key={field.name}>
                  <strong>{i[field.name]}: </strong>
                  {field.source
                    ? label(
                        query.data[field.source].find(
                          (item) => item.id === value(record, field.name),
                        ) ?? record,
                      )
                    : field.kind === "datetime-local"
                      ? new Date(value(record, field.name)).toLocaleString(
                          locale,
                          { timeZone: site.timezone },
                        )
                      : field.kind === "checkbox"
                        ? (record as unknown as Record<string, unknown>)[
                            field.name
                          ]
                          ? i.yes
                          : i.no
                        : value(record, field.name)}
                </p>
              ))}
            {manager && !evidence && (
              <details>
                <summary>{i.edit}</summary>
                <form
                  className="admin-form"
                  onSubmit={(event) =>
                    submit(
                      event,
                      editFields,
                      base + resource + `/${record.id}/`,
                      "PATCH",
                    )
                  }
                >
                  {renderFields(editFields, record)}
                  <button disabled={busy}>{t.save}</button>
                </form>
              </details>
            )}
            {manager && "archived" in record && (
              <button
                disabled={busy}
                onClick={() =>
                  void command(
                    base + resource + `/${record.id}/`,
                    { archived: !record.archived },
                    "PATCH",
                  )
                }
              >
                {record.archived ? t.restore : t.archive}
              </button>
            )}
            {manager && "state" in record && record.state !== "retired" && (
              <div className="admin-form">
                {(record.state === "planned" ||
                  record.state === "degraded") && (
                  <button
                    disabled={busy}
                    onClick={() =>
                      void command(
                        base + resource + `/${record.id}/transition/`,
                        { target: "commissioning" },
                      )
                    }
                  >
                    {i.start}
                  </button>
                )}
                {record.state === "commissioning" && (
                  <button
                    disabled={busy}
                    onClick={() =>
                      void command(
                        base + resource + `/${record.id}/transition/`,
                        { target: "degraded" },
                      )
                    }
                  >
                    {i.degrade}
                  </button>
                )}
                <button
                  disabled={busy}
                  onClick={() =>
                    void command(
                      base + resource + `/${record.id}/transition/`,
                      { target: "retired" },
                    )
                  }
                >
                  {i.retire}
                </button>
              </div>
            )}
            {qa && resource === "commissioning" && (
              <button
                disabled={busy}
                onClick={() =>
                  void command(base + `commissioning/${record.id}/accept/`)
                }
              >
                {i.review}
              </button>
            )}
            {resource === "acceptances" && (
              <>
                <p>{i.accepted}</p>
                {"current" in record && !record.current && (
                  <p role="status">{i.outdated}</p>
                )}
                <code className="secret">{value(record, "evidence_hash")}</code>
              </>
            )}
          </section>
        );
      })}
    </>
  );
}
