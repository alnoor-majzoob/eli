import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

/** Permission names mirror `apps/api/eil/modules/seed_data.py`. */
export const PERMISSIONS = {
  DASHBOARD_VIEW: "dashboard.view",
  WORK_VIEW: "work.view",
  WORK_EDIT: "work.edit",
  DEMAND_CREATE: "demand.create",
  DEMAND_APPROVE: "demand.approve",
  DEPT_HEAD_APPROVE: "dept_head.approve",
  SCORING_EDIT: "scoring.edit",
  PRIORITY_OVERRIDE: "priority.override",
  AI_REVIEW: "ai.review",
  ALLOCATION_MANAGE: "allocation.manage",
  SCENARIO_PROMOTE: "scenario.promote",
  CONNECTOR_MANAGE: "connector.manage",
  SOURCE_APPROVE: "source.approve",
  AUDIT_VIEW: "audit.view",
  ASSISTANT_USE: "assistant.use",
  RBAC_ADMIN: "rbac.admin",
} as const;

export type Permission = (typeof PERMISSIONS)[keyof typeof PERMISSIONS];
export type PermissionScope = "global" | "own_org" | "none";

export interface EffectivePermissions {
  roles: string[];
  org_unit_id: string | null;
  is_admin: boolean;
  permissions: Record<string, PermissionScope>;
}

export const EMPTY_PERMISSIONS: EffectivePermissions = {
  roles: [],
  org_unit_id: null,
  is_admin: false,
  permissions: {},
};

export async function fetchEffectivePermissions(): Promise<EffectivePermissions> {
  const { data, response } = await api.GET("/api/v1/me/permissions" as never, undefined as never);
  if (!response.ok || !data) return EMPTY_PERMISSIONS;
  return (data ?? EMPTY_PERMISSIONS) as EffectivePermissions;
}

/** react-query hook for the current principal's effective permissions. */
export function usePermissions(): {
  permissions: EffectivePermissions;
  isLoading: boolean;
  can: (permission: Permission | string, orgUnitId?: string | null) => boolean;
  hasRole: (role: string) => boolean;
  isAdmin: boolean;
  scope: (permission: Permission | string) => PermissionScope;
} {
  const query = useQuery({
    queryKey: ["me", "permissions"],
    queryFn: fetchEffectivePermissions,
    retry: false,
    staleTime: 30_000,
  });
  const permissions = query.data ?? EMPTY_PERMISSIONS;
  return {
    permissions,
    isLoading: query.isLoading,
    can: (permission, orgUnitId) => can(permissions, permission, orgUnitId),
    hasRole: (role) => permissions.roles.includes(role),
    isAdmin: permissions.is_admin,
    scope: (permission) => permissions.permissions[permission] ?? "none",
  };
}

/** Pure permission check. `orgUnitId` refines `own_org` scope against a target. */
export function can(
  permissions: EffectivePermissions,
  permission: Permission | string,
  orgUnitId?: string | null,
): boolean {
  if (permissions.is_admin) return true;
  const scope = permissions.permissions[permission] ?? "none";
  if (scope === "none") return false;
  if (scope === "global") return true;
  // own_org: allowed when no target org given (caller relies on backend) or target matches own org.
  if (orgUnitId === undefined) return true;
  return orgUnitId !== null && orgUnitId === permissions.org_unit_id;
}

export function hasRole(permissions: EffectivePermissions, role: string): boolean {
  return permissions.roles.includes(role);
}

