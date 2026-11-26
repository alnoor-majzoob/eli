import { useTranslation } from "react-i18next";
import { isRouteErrorResponse, useRouteError } from "react-router-dom";

export function RouteErrorPage() {
  const error = useRouteError();
  const { t } = useTranslation();

  const detail = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : "Unexpected routing error";

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-lg rounded-xl border bg-card p-8 shadow-sm">
        <h1 className="text-lg font-semibold">{t("common.error")}</h1>
        <p className="mt-2 break-words text-sm text-muted-foreground">{detail}</p>
        <button
          type="button"
          onClick={() => window.location.assign("/")}
          className="mt-6 inline-flex h-10 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
        >
          {t("common.backHome")}
        </button>
      </div>
    </div>
  );
}
