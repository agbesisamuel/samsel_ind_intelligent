/** Same-origin session transport. Secrets stay in memory; every mutation obtains fresh CSRF. */
import type { components } from "../../../../packages/api-contracts/schema";

export type Me = components["schemas"]["Me"];
export type Organisation = components["schemas"]["Organisation"];
export type Site = components["schemas"]["Site"];
export type Member = components["schemas"]["Membership"];
export type Invitation = components["schemas"]["Invitation"];
export type Audit = components["schemas"]["Audit"];
export type AuthResult = components["schemas"]["AuthResult"];
export type Page<T> = { count: number; next: string | null; results: T[] };

/** Preserve only an HTTP status for localized errors, never reflect server input or tokens. */
export class ApiFailure extends Error {
  constructor(public status: number) {
    super("Request failed");
  }
}

/** Enforce local API paths and bounded waits. Cookies are inaccessible to application code. */
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  if (!path.startsWith("/api/v1/") || path.includes("#") || path.includes("//"))
    throw new Error("Invalid API path");
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") {
    const csrf = await api<{ csrf_token: string }>("/api/v1/auth/csrf/");
    headers["X-CSRFToken"] = csrf.csrf_token;
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(path, {
    method,
    headers,
    credentials: "same-origin",
    cache: "no-store",
    signal: AbortSignal.timeout(10000),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw new ApiFailure(response.status);
  return response.status === 204
    ? (undefined as T)
    : (response.json() as Promise<T>);
}

/** Convert bounded pagination to a local query only; never follow an arbitrary next origin. */
export async function collection<T>(path: string): Promise<T[]> {
  const items: T[] = [];
  let next: string | null = path;
  while (next) {
    const page: Page<T> = await api<Page<T>>(next);
    items.push(...page.results);
    if (page.next) {
      const url = new URL(page.next, window.location.origin);
      if (url.pathname !== path || items.length > 10000)
        throw new Error("Invalid pagination");
      next = url.pathname + url.search;
    } else next = null;
  }
  return items;
}

/** Send bounded multipart evidence with fresh CSRF; the server validates type, scope and revision. */
export async function upload<T>(path: string, body: FormData): Promise<T> {
  if (!path.startsWith("/api/v1/") || path.includes("//") || path.includes("#"))
    throw new Error("Invalid API path");
  const csrf = await api<{ csrf_token: string }>("/api/v1/auth/csrf/");
  const response = await fetch(path, {
    method: "POST",
    body,
    credentials: "same-origin",
    cache: "no-store",
    headers: { "X-CSRFToken": csrf.csrf_token },
    signal: AbortSignal.timeout(30000),
  });
  if (!response.ok) throw new ApiFailure(response.status);
  return response.json() as Promise<T>;
}

/** Download only an authorized same-origin response; revoke the temporary blob URL immediately. */
export async function download(path: string, filename: string): Promise<void> {
  if (!path.startsWith("/api/v1/") || path.includes("//") || path.includes("#"))
    throw new Error("Invalid API path");
  const response = await fetch(path, {
    credentials: "same-origin",
    cache: "no-store",
    signal: AbortSignal.timeout(30000),
  });
  if (!response.ok) throw new ApiFailure(response.status);
  const url = URL.createObjectURL(await response.blob());
  try {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
  } finally {
    URL.revokeObjectURL(url);
  }
}
