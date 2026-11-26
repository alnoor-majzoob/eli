import { useTranslation } from "react-i18next";
import { Link, Navigate, Outlet } from "react-router-dom";

import { FullScreenLoader, useAuth } from "@/lib/auth";

export function RequireAuth() {
  const { status } = useAuth();

  if (status === "loading") {
    return <FullScreenLoader />;
  }

  if (status !== "authenticated") {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}

export function AuthCallbackPage() {
  const { status, authMode } = useAuth();
  const { t } = useTranslation();

  if (status === "authenticated") {
    return <Navigate to="/" replace />;
  }

  if (authMode === "dev") {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-background">
      <div className="size-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      <p className="text-sm text-muted-foreground">{t("auth.signingIn")}</p>
    </div>
  );
}

export function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <div className="mx-auto flex max-w-md flex-col items-center py-24 text-center">
      <p className="text-sm font-semibold uppercase tracking-wide text-primary">404</p>
      <h2 className="mt-2 text-2xl font-semibold">{t("common.notFoundTitle")}</h2>
      <p className="mt-2 text-sm text-muted-foreground">{t("common.notFoundBody")}</p>
      <Link
        to="/"
        className="mt-6 inline-flex h-10 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
      >
        {t("common.backHome")}
      </Link>
    </div>
  );
}
