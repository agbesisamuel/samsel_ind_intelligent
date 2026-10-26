/** Invite-only identity UI; passwords, bearer links and MFA material never enter browser storage. */
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
  type FormEvent,
} from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiFailure, type AuthResult, type Me } from "../api/identity";
import { useLocale } from "../i18n/LocaleProvider";
import { identityMessages } from "./identityMessages";

const IdentityContext = createContext<{
  user: Me | null;
  refresh: () => Promise<void>;
  loading: boolean;
} | null>(null);

/** Refresh assurance periodically; clear all tenant caches on an identity transition. */
export function IdentityProvider({ children }: { children: ReactNode }) {
  const cache = useQueryClient();
  const me = useQuery({
    queryKey: ["identity"],
    queryFn: () => api<Me>("/api/v1/me/"),
    retry: false,
    refetchInterval: 30000,
  });
  /** Discard previously scoped data before reloading the current authenticated identity. */
  async function refresh() {
    cache.removeQueries({
      predicate: (query) => query.queryKey[0] !== "identity",
    });
    await me.refetch();
  }
  return (
    <IdentityContext.Provider
      value={{
        user: me.isError ? null : (me.data ?? null),
        loading: me.isPending,
        refresh,
      }}
    >
      {children}
    </IdentityContext.Provider>
  );
}

/** Require explicit identity wiring; client visibility never replaces server permissions. */
export function useIdentity() {
  const context = useContext(IdentityContext);
  if (!context) throw new Error("IdentityProvider required");
  return context;
}

/** Read the selected complete dictionary without persisting sensitive state. */
export function useIdentityMessages() {
  return identityMessages[useLocale().locale];
}

/** Convert untrusted failure details into bounded, localized user guidance. */
export function failureText(
  error: unknown,
  t: ReturnType<typeof useIdentityMessages>,
) {
  return error instanceof ApiFailure && error.status === 429
    ? t.limited
    : t.failed;
}

/** Shared native field with an explicit label, bounded input, and no default secret value. */
export function Field({
  name,
  label,
  type = "text",
  value,
  required = true,
}: {
  name: string;
  label: string;
  type?: string;
  value?: string;
  required?: boolean;
}) {
  return (
    <label className="form-field">
      {label}
      <input
        name={name}
        type={type}
        defaultValue={value}
        required={required}
        maxLength={type === "password" ? 256 : 254}
        autoComplete={
          type === "password"
            ? "current-password"
            : name === "email"
              ? "email"
              : "off"
        }
      />
    </label>
  );
}

/** Keep sign-out available even when a security-version change revoked the session. */
export function IdentityMenu() {
  const { user, refresh } = useIdentity();
  const t = useIdentityMessages();
  const [error, setError] = useState("");
  const navigate = useNavigate();
  return (
    <>
      <span>{user?.email}</span>
      {user ? (
        <button
          onClick={async () => {
            try {
              await api("/api/v1/auth/logout/", "POST");
              await refresh();
              navigate("/login");
            } catch (error) {
              setError(failureText(error, t));
            }
          }}
        >
          {t.logout}
        </button>
      ) : (
        <Link to="/login">{t.login}</Link>
      )}
      {error && <span role="alert">{error}</span>}
    </>
  );
}

/** Run login, email proof, reset, enrollment and one-time recovery as explicit states. */
export function AuthPage({
  mode = "login",
}: {
  mode?: "login" | "accept" | "reset" | "security";
}) {
  const { user, refresh } = useIdentity();
  const t = useIdentityMessages();
  const navigate = useNavigate();
  const [state, setState] = useState("initial");
  const [secret, setSecret] = useState("");
  const [codes, setCodes] = useState<string[]>([]);
  const [token] = useState(
    () => new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "",
  );
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    // A fragment is never sent to the server. Remove it before navigation/referrer sharing.
    if (window.location.hash)
      window.history.replaceState(null, "", window.location.pathname);
  }, []);

  /** Submit one proof, erase password fields on success, and follow the server's next state. */
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = Object.fromEntries(new FormData(form));
    setBusy(true);
    setMessage("");
    try {
      let path: string;
      let body: unknown = fields;
      if (state === "mfa" || state === "enroll") path = "mfa/verify/";
      else if (state === "forgot") path = "password-reset/request/";
      else if (mode === "accept") {
        path = "invitations/accept/";
        body = { ...fields, token: token || fields.token };
      } else if (mode === "reset") {
        path = "password-reset/confirm/";
        body = { ...fields, token: token || fields.token };
      } else if (mode === "security")
        path = user?.mfa_enabled ? "step-up/" : "mfa/enroll/";
      else path = "login/";
      let result = await api<AuthResult>(`/api/v1/auth/${path}`, "POST", body);
      form.reset();
      if (result.state === "enroll") {
        if (!result.secret)
          result = await api<AuthResult>(
            "/api/v1/auth/mfa/enroll/",
            "POST",
            {},
          );
        setSecret(result.secret ?? "");
        setState("enroll");
      } else if (result.state === "mfa") setState("mfa");
      else if (result.recovery_codes) {
        setSecret("");
        setCodes(result.recovery_codes);
        setState("recovery");
      } else if (result.state === "accepted") setMessage(t.sent);
      else if (mode === "security") {
        setMessage(t.confirmed);
        await refresh();
      } else {
        await refresh();
        navigate(result.state === "signed_out" ? "/login" : "/sites");
      }
    } catch (error) {
      setMessage(failureText(error, t));
    } finally {
      setBusy(false);
    }
  }
  if (state === "recovery")
    return (
      <section className="workspace">
        <h1>{t.recovery}</h1>
        <p>{t.recoveryHelp}</p>
        <ul>
          {codes.map((code) => (
            <li key={code}>
              <code>{code}</code>
            </li>
          ))}
        </ul>
        <button
          onClick={async () => {
            setCodes([]);
            await refresh();
            navigate("/sites");
          }}
        >
          {t.saved}
        </button>
      </section>
    );
  const factor = state === "mfa" || state === "enroll";
  return (
    <section className="workspace">
      <h1>
        {factor
          ? state === "enroll"
            ? t.enroll
            : t.login
          : mode === "accept"
            ? t.invite
            : mode === "reset"
              ? t.reset
              : mode === "security"
                ? t.security
                : t.login}
      </h1>
      <p>{mode === "security" ? t.stepHelp : t.localMail}</p>
      {state === "enroll" && (
        <p>
          {t.enrollHelp}
          <br />
          <code className="secret">{secret}</code>
        </p>
      )}
      <form key={`${mode}-${state}`} className="admin-form" onSubmit={submit}>
        {!factor && (state === "forgot" || mode === "login") && (
          <Field name="email" label={t.email} type="email" />
        )}
        {!factor && state !== "forgot" && (
          <Field name="password" label={t.password} type="password" />
        )}
        {!factor && !token && (mode === "accept" || mode === "reset") && (
          <Field name="token" label={t.token} />
        )}
        {(factor || (mode === "security" && user?.mfa_enabled)) && (
          <Field name="code" label={t.code} />
        )}
        <button disabled={busy}>{busy ? t.loading : t.submit}</button>
      </form>
      {message && <p role="alert">{message}</p>}
      {mode === "login" && state === "initial" && (
        <button onClick={() => setState("forgot")}>{t.forgot}</button>
      )}
      {state === "forgot" && (
        <button
          onClick={() => {
            setState("initial");
            setMessage("");
          }}
        >
          {t.login}
        </button>
      )}
      {(mode === "accept" || mode === "reset") && (
        <Link to="/login">{t.login}</Link>
      )}
    </section>
  );
}
