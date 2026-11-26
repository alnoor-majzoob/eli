import { ChevronDown, LogOut, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/lib/auth";
import { cn, initials } from "@/lib/utils";

export function UserMenu() {
  const { principal, logout } = useAuth();
  const { t } = useTranslation();

  if (!principal) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="flex items-center gap-2 rounded-full border bg-card py-1 pe-2 ps-1 text-sm shadow-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label={t("header.openMenu")}
        data-testid="user-menu-trigger"
      >
        <span className="flex size-8 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
          {initials(principal.name)}
        </span>
        <span className="hidden max-w-40 truncate font-medium sm:block">{principal.name}</span>
        <ChevronDown className="size-3.5 text-muted-foreground" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel>{t("header.signedInAs")}</DropdownMenuLabel>
        <div className="px-2.5 pb-2">
          <p className="truncate text-sm font-semibold">{principal.name}</p>
          <p className="truncate text-xs text-muted-foreground">{principal.email}</p>
          <div className="mt-2 flex flex-wrap gap-1">
            {(principal.roles ?? []).map((role) => (
              <span
                key={role}
                className="inline-flex items-center gap-1 rounded-full bg-accent px-2 py-0.5 text-[11px] font-medium text-accent-foreground"
              >
                <ShieldCheck className="size-3" />
                {t(`roles.${role}`, { defaultValue: role })}
              </span>
            ))}
          </div>
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={logout}
          className={cn("text-destructive focus:text-destructive")}
          data-testid="logout"
        >
          <LogOut className="size-4" />
          {t("header.signOut")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
