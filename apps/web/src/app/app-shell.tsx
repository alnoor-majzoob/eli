import {
  BarChart2,
  FolderKanban,
  GitMerge,
  Inbox,
  LayoutDashboard,
  ListChecks,
  Menu,
  Monitor,
  PlugZap,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
  TriangleAlert,
  X,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet } from "react-router-dom";

import { ReplayBadge } from "@/components/badges";
import { LanguageToggle } from "@/components/language-toggle";
import { ThemeToggle } from "@/components/theme-toggle";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { UserMenu } from "@/components/user-menu";
import { PERMISSIONS, usePermissions } from "@/lib/permissions";
import { usePlatformConfig } from "@/lib/platform";
import { cn } from "@/lib/utils";

interface NavEntry {
  key: string;
  icon: LucideIcon;
  to?: string;
  /** Permission required to see this entry; hidden when not granted. */
  permission?: string;
}

const NAV_GROUPS: { labelKey: string; items: NavEntry[] }[] = [
  {
    labelKey: "nav.sectionWorkspace",
    items: [
      { key: "overview", icon: LayoutDashboard, to: "/", permission: PERMISSIONS.DASHBOARD_VIEW },
      { key: "objectives", icon: Target, to: "/objectives", permission: PERMISSIONS.WORK_VIEW },
      { key: "demand", icon: Inbox, to: "/demand", permission: PERMISSIONS.WORK_VIEW },
      { key: "portfolio", icon: FolderKanban, to: "/portfolio", permission: PERMISSIONS.WORK_VIEW },
      { key: "tasks", icon: ListChecks, to: "/tasks", permission: PERMISSIONS.WORK_VIEW },
      { key: "capacity", icon: BarChart2, to: "/capacity", permission: PERMISSIONS.WORK_VIEW },
      { key: "executive", icon: TrendingUp, to: "/executive", permission: PERMISSIONS.DASHBOARD_VIEW },
      { key: "presenter", icon: Monitor, to: "/executive/presenter", permission: PERMISSIONS.DASHBOARD_VIEW },
      { key: "risk", icon: TriangleAlert, to: "/risk", permission: PERMISSIONS.WORK_VIEW },
      { key: "prioritization", icon: ShieldCheck, to: "/prioritization", permission: PERMISSIONS.WORK_VIEW },
      { key: "graph", icon: GitMerge, to: "/graph", permission: PERMISSIONS.WORK_VIEW },
      { key: "aiInbox", icon: Sparkles, to: "/ai/inbox", permission: PERMISSIONS.WORK_VIEW },
      { key: "connectors", icon: PlugZap, to: "/admin/connectors", permission: PERMISSIONS.CONNECTOR_MANAGE },
    ],
  },
  {
    labelKey: "nav.sectionGovernance",
    items: [
      { key: "approvals", icon: Sparkles, to: "/approvals", permission: PERMISSIONS.WORK_VIEW },
      { key: "audit", icon: ShieldAlert, to: "/audit", permission: PERMISSIONS.AUDIT_VIEW },
    ],
  },
];

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation();
  const { can } = usePermissions();

  const groups = NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => !item.permission || can(item.permission)),
  })).filter((group) => group.items.length > 0);

  return (
    <div className="flex h-full flex-col bg-sidebar text-sidebar-foreground">
      <div className="flex h-16 items-center gap-3 border-b border-sidebar-border px-5">
        <div className="flex size-9 items-center justify-center rounded-lg bg-primary text-sm font-bold text-primary-foreground">
          EIL
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">{t("app.name")}</p>
          <p className="truncate text-[11px] text-sidebar-muted">{t("app.tagline")}</p>
        </div>
      </div>

      <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-5" aria-label="Primary">
        {groups.map((group) => (
          <div key={group.labelKey}>
            <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-sidebar-muted">
              {t(group.labelKey)}
            </p>
            <ul className="space-y-1">
              {group.items.map((item) => {
                const Icon = item.icon;
                if (!item.to) {
                  return (
                    <li key={item.key}>
                      <div
                        className="flex cursor-not-allowed items-center gap-3 rounded-md px-3 py-2 text-sm text-sidebar-muted/80"
                        aria-disabled="true"
                        title={t("common.comingSoon")}
                      >
                        <Icon className="size-4 shrink-0" />
                        <span className="flex-1 truncate">{t(`nav.${item.key}`)}</span>
                        <span className="rounded-full border border-sidebar-border px-1.5 py-px text-[9px] uppercase tracking-wide">
                          {t("nav.soon")}
                        </span>
                      </div>
                    </li>
                  );
                }
                return (
                  <li key={item.key}>
                    <NavLink
                      to={item.to}
                      end
                      onClick={onNavigate}
                      className={({ isActive }) =>
                        cn(
                          "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                          isActive
                            ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                            : "text-sidebar-foreground/85 hover:bg-sidebar-accent hover:text-sidebar-foreground",
                        )
                      }
                    >
                      <Icon className="size-4 shrink-0" />
                      <span className="truncate">{t(`nav.${item.key}`)}</span>
                    </NavLink>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="border-t border-sidebar-border p-4">
        <p className="text-[11px] leading-relaxed text-sidebar-muted">{t("app.description")}</p>
        <div className="mt-3 flex items-center gap-2">
          <Badge variant="outline" className="border-sidebar-border text-sidebar-muted">
            {t("common.phase", { number: 5 })}
          </Badge>
          <ReplayBadge />
        </div>
      </div>
    </div>
  );
}

export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { t } = useTranslation();
  const { data: config } = usePlatformConfig();

  const showReplay = config ? !config.ai_enabled || config.llm_mode === "replay" : false;

  return (
    <div className="min-h-screen bg-background">
      <aside className="fixed inset-y-0 start-0 z-40 hidden w-64 lg:block">
        <Sidebar />
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label={t("common.close")}
            className="absolute inset-0 bg-slate-950/60"
            onClick={() => setMobileOpen(false)}
          />
          <div className="absolute inset-y-0 start-0 w-72 shadow-2xl">
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              className="absolute end-3 top-3 z-10 rounded-md p-1.5 text-sidebar-muted hover:bg-sidebar-accent"
              aria-label={t("common.close")}
            >
              <X className="size-4" />
            </button>
            <Sidebar onNavigate={() => setMobileOpen(false)} />
          </div>
        </div>
      )}

      <div className="flex min-h-screen flex-col lg:ps-64">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b bg-background/90 px-4 backdrop-blur sm:px-6">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setMobileOpen(true)}
            aria-label={t("nav.overview")}
            data-testid="mobile-menu"
          >
            <Menu className="size-5" />
          </Button>

          <div className="min-w-0 flex-1">
            <h1 className="truncate text-base font-semibold">{t("home.title")}</h1>
            <p className="hidden truncate text-xs text-muted-foreground sm:block">
              {t("app.description")}
            </p>
          </div>

          <div className="flex items-center gap-1.5">
            {config && (
              <Badge variant="muted" className="hidden uppercase sm:inline-flex">
                {config.app_env}
              </Badge>
            )}
            {showReplay && <ReplayBadge className="hidden sm:inline-flex" />}
            <LanguageToggle />
            <ThemeToggle />
            <div className="mx-1 h-6 w-px bg-border" />
            <UserMenu />
          </div>
        </header>

        <main className="flex-1 p-4 sm:p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
