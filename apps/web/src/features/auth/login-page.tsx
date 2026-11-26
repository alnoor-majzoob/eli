import { CheckCircle2, ShieldCheck, Sparkles, Workflow } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Navigate } from "react-router-dom";

import { LanguageToggle } from "@/components/language-toggle";
import { ThemeToggle } from "@/components/theme-toggle";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";

export function LoginPage() {
  const { status, login, authMode, devRoles, error } = useAuth();
  const { t } = useTranslation();
  const [role, setRole] = useState("executive");
  const [localError, setLocalError] = useState<string | null>(null);

  const effectiveRole = devRoles.some((entry) => entry.role === role)
    ? role
    : (devRoles[0]?.role ?? "executive");

  if (status === "authenticated") {
    return <Navigate to="/" replace />;
  }

  const submitting = status === "loading";
  const selectedRole = devRoles.find((entry) => entry.role === effectiveRole);
  const message = localError ?? error;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLocalError(null);
    try {
      await login(effectiveRole);
    } catch (cause) {
      setLocalError(cause instanceof Error ? cause.message : t("auth.invalid"));
    }
  }

  return (
    <div className="grid min-h-screen bg-background lg:grid-cols-[1.05fr_0.95fr]">
      <section className="relative hidden overflow-hidden bg-sidebar p-12 text-sidebar-foreground lg:flex lg:flex-col lg:justify-between">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 opacity-70"
          style={{
            backgroundImage:
              "radial-gradient(circle at 15% 20%, rgba(20,184,166,0.22), transparent 32%), radial-gradient(circle at 85% 75%, rgba(59,130,246,0.16), transparent 38%)",
          }}
        />
        <div className="relative">
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-lg bg-primary text-sm font-bold text-primary-foreground">
              EIL
            </div>
            <div>
              <p className="text-sm font-semibold">{t("app.name")}</p>
              <p className="text-xs text-sidebar-muted">{t("app.tagline")}</p>
            </div>
          </div>

          <h1 className="mt-20 max-w-lg text-4xl font-semibold leading-tight tracking-tight">
            {t("auth.brandHeadline")}
          </h1>

          <ul className="mt-10 space-y-4 text-sm text-sidebar-foreground/85">
            {[t("auth.brandPointOne"), t("auth.brandPointTwo"), t("auth.brandPointThree")].map(
              (point) => (
                <li key={point} className="flex items-start gap-3">
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-sidebar-accent-foreground" />
                  <span>{point}</span>
                </li>
              ),
            )}
          </ul>
        </div>

        <div className="relative flex flex-wrap items-center gap-2 text-[11px] text-sidebar-muted">
          <Badge variant="outline" className="border-sidebar-border text-sidebar-muted">
            {t("common.phase", { number: 0 })}
          </Badge>
          <span>{t("auth.syntheticNote")}</span>
        </div>
      </section>

      <section className="relative flex items-center justify-center p-6 sm:p-10">
        <div className="absolute end-4 top-4 flex items-center gap-1">
          <LanguageToggle />
          <ThemeToggle />
        </div>

        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <div className="flex size-10 items-center justify-center rounded-lg bg-primary text-sm font-bold text-primary-foreground">
              EIL
            </div>
            <div>
              <p className="text-sm font-semibold">{t("app.name")}</p>
              <p className="text-xs text-muted-foreground">{t("app.tagline")}</p>
            </div>
          </div>

          <div className="rounded-2xl border bg-card p-8 shadow-sm">
            <div className="mb-6">
              <div className="mb-4 flex size-11 items-center justify-center rounded-xl bg-accent text-accent-foreground">
                {authMode === "oidc" ? (
                  <ShieldCheck className="size-5" />
                ) : (
                  <Sparkles className="size-5" />
                )}
              </div>
              <h2 className="text-xl font-semibold tracking-tight">
                {authMode === "oidc" ? t("auth.sso") : t("auth.devTitle")}
              </h2>
              <p className="mt-2 text-sm text-muted-foreground">{t("auth.devHint")}</p>
            </div>

            {authMode === "oidc" ? (
              <Button
                className="w-full"
                onClick={() => void login()}
                disabled={submitting}
                data-testid="login-submit"
              >
                <ShieldCheck className="size-4" />
                {submitting ? t("auth.signingIn") : t("auth.sso")}
              </Button>
            ) : (
              <form className="space-y-4" onSubmit={handleSubmit}>
                <div className="space-y-1.5">
                  <label htmlFor="role" className="text-sm font-medium">
                    {t("auth.role")}
                  </label>
                  <select
                    id="role"
                    data-testid="role-select"
                    value={effectiveRole}
                    onChange={(event) => setRole(event.target.value)}
                    className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {devRoles.map((entry) => (
                      <option key={entry.role} value={entry.role}>
                        {t(`roles.${entry.role}`, { defaultValue: entry.role })} — {entry.name}
                      </option>
                    ))}
                  </select>
                  {selectedRole && (
                    <p className="text-xs text-muted-foreground">
                      {selectedRole.email} · {selectedRole.org_unit_id}
                    </p>
                  )}
                </div>

                <Button
                  type="submit"
                  className="w-full"
                  disabled={submitting}
                  data-testid="login-submit"
                >
                  <Workflow className="size-4" />
                  {submitting ? t("auth.signingIn") : t("auth.signIn")}
                </Button>
              </form>
            )}

            {message && (
              <p
                role="alert"
                aria-live="polite"
                className="mt-4 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
              >
                {message}
              </p>
            )}
          </div>

          <p className="mt-6 text-center text-xs text-muted-foreground">
            {t("auth.syntheticNote")}
          </p>
        </div>
      </section>
    </div>
  );
}
