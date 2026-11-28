import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

export function ForbiddenPage() {
  const { t } = useTranslation();
  return (
    <div className="mx-auto flex max-w-md flex-col items-center py-24 text-center">
      <p className="text-sm font-semibold uppercase tracking-wide text-destructive">403</p>
      <h2 className="mt-2 text-2xl font-semibold">{t("forbidden.title")}</h2>
      <p className="mt-2 text-sm text-muted-foreground">{t("forbidden.body")}</p>
      <Link
        to="/"
        className="mt-6 inline-flex h-10 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
      >
        {t("common.backHome")}
      </Link>
    </div>
  );
}
