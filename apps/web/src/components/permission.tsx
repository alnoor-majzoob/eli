import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { FullScreenLoader } from "@/lib/auth";
import { can, type Permission, usePermissions } from "@/lib/permissions";

/** Render children only when the current user has `permission`. */
export function Can({
  permission,
  orgUnitId,
  children,
  fallback = null,
}: {
  permission: Permission | string;
  orgUnitId?: string | null;
  children: ReactNode;
  fallback?: ReactNode;
}) {
  const { permissions, isLoading } = usePermissions();
  if (isLoading) return null;
  return can(permissions, permission, orgUnitId) ? <>{children}</> : <>{fallback}</>;
}

/** Route guard: require a permission to render nested routes. */
export function RequirePermission({ permission }: { permission: Permission | string }) {
  const { permissions, isLoading } = usePermissions();
  const location = useLocation();

  if (isLoading) return <FullScreenLoader />;
  if (!can(permissions, permission)) {
    return <Navigate to="/forbidden" replace state={{ from: location }} />;
  }
  return <Outlet />;
}
