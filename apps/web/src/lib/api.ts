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
  }
  return fallback;
}
