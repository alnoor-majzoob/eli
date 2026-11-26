import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function SimBadge({ className }: { className?: string }) {
  const { t } = useTranslation();
  return (
    <Badge
      variant="warning"
      className={cn("uppercase tracking-wide", className)}
      title={t("home.systemsBody")}
      data-testid="sim-badge"
    >
      {t("badges.sim")}
    </Badge>
  );
}

export function ReplayBadge({ className }: { className?: string }) {
  const { t } = useTranslation();
  return (
    <Badge
      variant="outline"
      className={cn(
        "border-primary/40 bg-primary/10 uppercase tracking-wide text-primary",
        className,
      )}
      data-testid="replay-badge"
    >
      {t("badges.replay")}
    </Badge>
  );
}

export function SyntheticBadge({ className }: { className?: string }) {
  const { t } = useTranslation();
  return (
    <Badge
      variant="warning"
      className={cn("uppercase tracking-wide", className)}
      data-testid="synthetic-badge"
    >
      {t("badges.synthetic")}
    </Badge>
  );
}
