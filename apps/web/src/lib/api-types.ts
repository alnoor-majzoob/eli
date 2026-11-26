import type { components } from "@eil/api-client";

export type PlatformConfig = components["schemas"]["PlatformConfig"];
export type Principal = components["schemas"]["Principal"];
export type AuthConfigResponse = components["schemas"]["AuthConfigResponse"];
export type DemoRole = AuthConfigResponse["roles"][number];

export interface Health {
  status: string;
  app: string;
  version: string;
  env: string;
}

export interface Readiness {
  status: string;
  dependencies: Record<string, string>;
}
