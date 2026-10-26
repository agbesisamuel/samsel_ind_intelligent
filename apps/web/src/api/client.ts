/** Same-origin typed client generated from the committed OpenAPI contract. */
import createClient from "openapi-fetch";
import type { paths } from "../../../../packages/api-contracts/schema";

export const client = createClient<paths>({
  baseUrl: "",
  credentials: "same-origin",
});

/** Fail closed on HTTP, malformed status or network failure; abort after five seconds. */
export async function fetchHealth(): Promise<boolean> {
  const { data, error } = await client.GET("/api/v1/health/", {
    signal: AbortSignal.timeout(5000),
  });
  if (error || data?.status !== "ok") throw new Error("API unavailable");
  return true;
}
