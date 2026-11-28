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

/** Error thrown for non-2xx API responses (RFC-9457 problem body attached). */
export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;
  constructor(status: number, body: unknown, fallback: string) {
    super(problemMessage(body, fallback));
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
  get code(): string | null {
    return problemCode(this.body);
  }
  get isForbidden(): boolean {
    return this.status === 403 || isForbidden(this.body);
  }
}

/** Throw `ApiError` when an openapi-fetch result is not ok. */
export function ensureOk<T>(
  result: { data?: T; error?: unknown; response: Response },
  fallback = "Request failed",
): T {
  if (!result.response.ok) {
    throw new ApiError(result.response.status, result.error ?? null, fallback);
  }
  return (result.data ?? (undefined as T));
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
