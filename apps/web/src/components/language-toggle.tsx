import { Languages } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

export function LanguageToggle() {
  const { i18n, t } = useTranslation();
  const isArabic = i18n.resolvedLanguage?.startsWith("ar") ?? false;

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={() => void i18n.changeLanguage(isArabic ? "en" : "ar")}
      aria-label={t("header.language")}
      title={t("header.language")}
      data-testid="language-toggle"
      className="gap-1.5"
    >
      <Languages className="size-4" />
      <span className="text-xs font-semibold">{isArabic ? "EN" : "AR"}</span>
    </Button>
  );
}
