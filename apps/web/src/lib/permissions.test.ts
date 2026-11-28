import { describe, expect, it } from "vitest";

import { can, hasRole, PERMISSIONS, type EffectivePermissions } from "@/lib/permissions";

const base: EffectivePermissions = {
  roles: [],
  org_unit_id: null,
  is_admin: false,
  permissions: {},
};

describe("permission model", () => {
  it("admin can everything", () => {
    const admin: EffectivePermissions = { ...base, is_admin: true, roles: ["admin"] };
    expect(can(admin, PERMISSIONS.WORK_EDIT)).toBe(true);
    expect(can(admin, PERMISSIONS.CONNECTOR_MANAGE)).toBe(true);
    expect(can(admin, PERMISSIONS.RBAC_ADMIN)).toBe(true);
  });

  it("denies missing permission", () => {
    expect(can(base, PERMISSIONS.WORK_EDIT)).toBe(false);
  });

  it("global scope allows any target", () => {
    const p: EffectivePermissions = { ...base, permissions: { "work.edit": "global" } };
    expect(can(p, PERMISSIONS.WORK_EDIT)).toBe(true);
    expect(can(p, PERMISSIONS.WORK_EDIT, "some-other-org")).toBe(true);
  });

  it("own_org scope only allows own org target", () => {
    const p: EffectivePermissions = {
      ...base,
      org_unit_id: "org-1",
      permissions: { "work.edit": "own_org" },
    };
    expect(can(p, PERMISSIONS.WORK_EDIT, "org-1")).toBe(true);
    expect(can(p, PERMISSIONS.WORK_EDIT, "org-2")).toBe(false);
    expect(can(p, PERMISSIONS.WORK_EDIT, null)).toBe(false);
  });

  it("read-only auditor has no write permissions", () => {
    const auditor: EffectivePermissions = {
      roles: ["auditor"],
      org_unit_id: null,
      is_admin: false,
      permissions: { "work.view": "global", "dashboard.view": "global", "audit.view": "global" },
    };
    expect(can(auditor, PERMISSIONS.WORK_VIEW)).toBe(true);
    expect(can(auditor, PERMISSIONS.WORK_EDIT)).toBe(false);
    expect(can(auditor, PERMISSIONS.DEMAND_CREATE)).toBe(false);
    expect(can(auditor, PERMISSIONS.AI_REVIEW)).toBe(false);
    expect(can(auditor, PERMISSIONS.DEMAND_APPROVE)).toBe(false);
    expect(can(auditor, PERMISSIONS.CONNECTOR_MANAGE)).toBe(false);
    expect(hasRole(auditor, "auditor")).toBe(true);
  });

  it("integration_admin is connector-only", () => {
    const ia: EffectivePermissions = {
      roles: ["integration_admin"],
      org_unit_id: null,
      is_admin: false,
      permissions: { "connector.manage": "global", "audit.view": "own_org" },
    };
    expect(can(ia, PERMISSIONS.CONNECTOR_MANAGE)).toBe(true);
    expect(can(ia, PERMISSIONS.WORK_VIEW)).toBe(false);
    expect(can(ia, PERMISSIONS.DASHBOARD_VIEW)).toBe(false);
    expect(can(ia, PERMISSIONS.WORK_EDIT)).toBe(false);
    expect(can(ia, PERMISSIONS.ALLOCATION_MANAGE)).toBe(false);
  });
});
