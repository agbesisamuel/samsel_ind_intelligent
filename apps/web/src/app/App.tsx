/** Accessible application shell with honest, auth-aware unavailable feature routes. */
import { Link, NavLink, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchHealth } from "../api/client";
import { useLocale } from "../i18n/LocaleProvider";
import {
  AuthPage,
  IdentityMenu,
  IdentityProvider,
  useIdentity,
  useIdentityMessages,
} from "./Identity";
import { Administration } from "./Administration";
import { InventoryPage } from "./Inventory";
import { MonitoringPage } from "./Monitoring";
import { RulesPage } from "./Rules";
import { NotificationsPage } from "./Notifications";
import { IncidentsPage } from "./Incidents";
import { ReportsPage } from "./Reports";
import { IntegrationsPage } from "./Integrations";
import { BillingPage } from "./Billing";
import { HelpPage } from "./Help";

/** Distinguish infrastructure availability from the absence of monitoring data. */
function Overview() {
  const { t } = useLocale();
  const health = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    retry: false,
  });
  return (
    <>
      <p className="eyebrow">{t.phase}</p>
      <h1>{t.welcome}</h1>
      <p className="intro">{t.intro}</p>
      <section className="connection" aria-labelledby="connection-title">
        <div>
          <h2 id="connection-title">{t.apiTitle}</h2>
          <p>{t.apiDetail}</p>
        </div>
        <div className="connection-actions">
          <span
            role="status"
            className={`status ${health.isError ? "error" : ""}`}
          >
            {health.isFetching
              ? t.checking
              : health.isError
                ? t.unavailable
                : t.connected}
          </span>
          <button
            onClick={() => void health.refetch()}
            disabled={health.isFetching}
          >
            {t.retry}
          </button>
        </div>
      </section>
      <section className="workspace" aria-labelledby="workspace-title">
        <div className="section-heading">
          <h2 id="workspace-title">{t.next}</h2>
          <span className="badge">{t.local}</span>
        </div>
        <div className="empty">
          <span className="empty-mark" aria-hidden="true">
            —
          </span>
          <h3>{t.emptyTitle}</h3>
          <p>{t.emptyDetail}</p>
        </div>
      </section>
    </>
  );
}

/** Explain unmatched client routes without exposing server or tenant identifiers. */
function NotFound() {
  const { t } = useLocale();
  return (
    <>
      <h1>{t.notFound}</h1>
      <p>{t.notFoundDetail}</p>
      <Link to="/">{t.return}</Link>
    </>
  );
}

/** Provide a shared session boundary to the responsive shell and protected screens. */
export function App() {
  return (
    <IdentityProvider>
      <AppShell />
    </IdentityProvider>
  );
}

/** Derive visible management links from live grants; the API remains the authority. */
function AppShell() {
  const { locale, setLocale, t } = useLocale();
  const { user } = useIdentity();
  const identity = useIdentityMessages();
  const roles =
    user?.memberships.flatMap((member) =>
      member.roles.map((role) => role.role),
    ) ?? [];
  return (
    <div className="shell">
      <a className="skip" href="#main">
        {t.skip}
      </a>
      <aside className="sidebar">
        <Link
          className="brand"
          to="/"
          aria-label="SAMSEL Industrial Intelligence"
        >
          <span className="brand-mark" aria-hidden="true">
            S
          </span>
          <span>
            <strong>SAMSEL</strong>
            <small>Industrial Intelligence</small>
          </span>
        </Link>
        <nav aria-label={t.navigation}>
          <NavLink end to="/">
            {t.overview}
          </NavLink>
          {user && (
            <>
              <NavLink to="/organisations">{identity.organisations}</NavLink>
              {roles.length > 0 && <NavLink to="/sites">{t.sites}</NavLink>}
              {roles.length > 0 && <NavLink to="/sensors">{t.sensors}</NavLink>}
              {roles.length > 0 && (
                <NavLink to="/readings">{t.readings}</NavLink>
              )}
              {roles.length > 0 && (
                <NavLink to="/rules">
                  {locale === "da" ? "Regler" : "Rules"}
                </NavLink>
              )}
              {roles.some((role) => ["owner", "site_admin"].includes(role)) && (
                <NavLink to="/users">{t.users}</NavLink>
              )}
              {roles.some((role) =>
                ["owner", "site_admin", "qa", "auditor"].includes(role),
              ) && <NavLink to="/audit">{identity.audit}</NavLink>}
              <NavLink to="/security">{identity.security}</NavLink>
              {roles.some((role) =>
                ["owner", "site_admin", "qa", "operations", "auditor"].includes(
                  role,
                ),
              ) && <NavLink to="/reports">{t.reports}</NavLink>}
              {roles.length > 0 && (
                <NavLink to="/incidents">{t.incidents}</NavLink>
              )}
              {roles.length > 0 && (
                <NavLink to="/notifications">
                  {locale === "da" ? "Notifikationer" : "Notifications"}
                </NavLink>
              )}
            </>
          )}
          {user && roles.length > 0 && (
            <NavLink to="/integrations">{t.integrations}</NavLink>
          )}
          {user && (user.platform_admin || roles.includes("owner")) && (
            <NavLink to="/billing">{t.billing}</NavLink>
          )}
          {user && roles.length > 0 && (
            <NavLink to="/help">
              {locale === "da" ? "Hjælp og support" : "Help and support"}
            </NavLink>
          )}
        </nav>
        <div className="sidebar-footer">
          {t.footer}
          <br />
          {t.scope}
        </div>
      </aside>
      <div className="body">
        <header className="topbar">
          <span className="local-label">{t.local}</span>
          <div className="toolbar">
            <IdentityMenu />
            <label>
              {t.language}
              <select
                value={locale}
                onChange={(event) =>
                  setLocale(event.target.value as "en" | "da")
                }
              >
                <option value="en">English</option>
                <option value="da">Dansk</option>
              </select>
            </label>
          </div>
        </header>
        <main id="main" tabIndex={-1}>
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/login" element={<AuthPage key="login" />} />
            <Route
              path="/accept"
              element={<AuthPage key="accept" mode="accept" />}
            />
            <Route
              path="/reset"
              element={<AuthPage key="reset" mode="reset" />}
            />
            <Route
              path="/security"
              element={<AuthPage key="security" mode="security" />}
            />
            <Route
              path="/settings"
              element={<AuthPage key="settings" mode="security" />}
            />
            <Route
              path="/organisations"
              element={<Administration section="organisations" />}
            />
            <Route path="/sites" element={<Administration section="sites" />} />
            <Route path="/sensors" element={<InventoryPage />} />
            <Route path="/readings" element={<MonitoringPage />} />
            <Route path="/rules" element={<RulesPage />} />
            <Route path="/notifications" element={<NotificationsPage />} />
            <Route path="/incidents" element={<IncidentsPage />} />
            <Route path="/actions" element={<IncidentsPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/integrations" element={<IntegrationsPage />} />
            <Route path="/users" element={<Administration section="users" />} />
            <Route path="/audit" element={<Administration section="audit" />} />
            <Route path="/billing" element={<BillingPage />} />
            <Route path="/help" element={<HelpPage />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
          <footer className="safety">
            <strong>{t.boundary}</strong>
            <p>{t.boundaryDetail}</p>
          </footer>
        </main>
      </div>
    </div>
  );
}
