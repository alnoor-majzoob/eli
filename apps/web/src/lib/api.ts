import createClient from "openapi-fetch";

import type { paths } from "@eil/api-client";

export const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

export const api = createClient<paths>({ baseUrl: apiBaseUrl });

let accessToken: string | null = null;

export function setApiToken(token: string | null): void {
  accessToken = token;
}

api.use({
  onRequest({ request }) {
    if (accessToken) {
      request.headers.set("Authorization", `Bearer ${accessToken}`);
    }
    request.headers.set("Accept", "application/json");
    return request;
  },
});

export function problemMessage(error: unknown, fallback: string): string {
  if (error && typeof error === "object") {
    const detail = (error as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim().length > 0) {
      return detail;
    }
    const title = (error as { title?: unknown }).title;
    if (typeof title === "string" && title.trim().length > 0) {
      return title;
    }
  }
  return fallback;
}

/** Machine-readable error code from an RFC-9457 problem body, if present. */
export function problemCode(error: unknown): string | null {
  if (error && typeof error === "object") {
    const code = (error as { code?: unknown }).code;
    if (typeof code === "string" && code.length > 0) return code;
  }
  return null;
}

/** True when an API error is an authorization denial (not "no data"). */
export function isForbidden(error: unknown): boolean {
  return problemCode(error) === "forbidden" || problemCode(error) === "sod_violation";
}
