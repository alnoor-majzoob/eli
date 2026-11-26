/** Shared enums/constants. Generated from the API in later phases where useful. */

export const APP_NAME = "EIL";

export const ROLES = [
  "executive",
  "portfolio_manager",
  "project_manager",
  "dept_head",
  "resource_manager",
  "team_member",
  "pmo_analyst",
  "ai_reviewer",
  "integration_admin",
  "auditor",
  "admin",
] as const;

export type Role = (typeof ROLES)[number];
