import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { AuthProvider as OidcProvider, useAuth as useOidcAuth } from "react-oidc-context";
import { useTranslation } from "react-i18next";

import { api, problemMessage, setApiToken } from "./api";
import type { AuthConfigResponse, DemoRole, Principal } from "./api-types";

export type AuthStatus = "loading" | "unauthenticated" | "authenticated" | "error";

export interface AuthContextValue {
  status: AuthStatus;
  principal: Principal | null;
  authMode: string | null;
  devRoles: DemoRole[];
  error: string | null;
  login: (role?: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}

export function FullScreenLoader({ label }: { label?: string }) {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background">
      <div className="flex size-12 items-center justify-center rounded-xl bg-primary/10">
        <div className="size-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
      <p className="text-sm text-muted-foreground">{label ?? t("common.loading")}</p>
    </div>
  );
}

function ConfigError({ message }: { message: string }) {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-md rounded-xl border bg-card p-8 text-center shadow-sm">
        <h1 className="text-lg font-semibold">{t("common.error")}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{message}</p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="mt-6 inline-flex h-10 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
        >
          {t("common.retry")}
        </button>
      </div>
    </div>
  );
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AuthConfigResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api
      .GET("/api/v1/auth/config")
      .then(({ data, error: requestError, response }) => {
        if (!active) return;
        if (response.ok && data) {
          setConfig(data);
          return;
        }
        setError(problemMessage(requestError, "Unable to load authentication configuration."));
      })
      .catch((cause: unknown) => {
        if (!active) return;
        setError(cause instanceof Error ? cause.message : "Unable to reach the API.");
      });
    return () => {
      active = false;
    };
  }, []);

  if (error) {
    return <ConfigError message={error} />;
  }

  if (!config) {
    return <FullScreenLoader />;
  }

  if (config.auth_mode === "oidc") {
    const authority = import.meta.env.VITE_OIDC_AUTHORITY ?? "http://localhost:8080/realms/eil";
    const clientId = import.meta.env.VITE_OIDC_CLIENT_ID ?? "eil-web";
    const redirectUri =
      import.meta.env.VITE_OIDC_REDIRECT_URI ?? `${window.location.origin}/auth/callback`;

    return (
      <OidcProvider
        authority={authority}
        client_id={clientId}
        redirect_uri={redirectUri}
        response_type="code"
        scope="openid profile email"
        onSigninCallback={() => {
          window.history.replaceState({}, document.title, "/");
        }}
      >
        <OidcAuthBridge roles={config.roles}>{children}</OidcAuthBridge>
      </OidcProvider>
    );
  }

  return <DevAuthProvider config={config}>{children}</DevAuthProvider>;
}

function DevAuthProvider({
  config,
  children,
}: {
  config: AuthConfigResponse;
  children: ReactNode;
}) {
  const [principal, setPrincipal] = useState<Principal | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const login = useCallback(async (role?: string) => {
    setBusy(true);
    setError(null);
    try {
      const {
        data,
        error: requestError,
        response,
      } = await api.POST("/api/v1/auth/dev-login", { body: { role: role ?? "executive" } });
      if (!response.ok || !data) {
        setError(problemMessage(requestError, "Sign-in failed."));
        return;
      }
      setApiToken(data.access_token);
      setToken(data.access_token);
      setPrincipal(data.principal);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  }, []);

  const logout = useCallback(() => {
    setApiToken(null);
    setToken(null);
    setPrincipal(null);
    setError(null);
  }, []);

  const status: AuthStatus = busy
    ? "loading"
    : principal && token
      ? "authenticated"
      : "unauthenticated";

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      principal,
      authMode: config.auth_mode,
      devRoles: config.roles,
      error,
      login,
      logout,
    }),
    [status, principal, config.auth_mode, config.roles, error, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

function OidcAuthBridge({ roles, children }: { roles: DemoRole[]; children: ReactNode }) {
  const oidc = useOidcAuth();

  useEffect(() => {
    setApiToken(oidc.user?.access_token ?? null);
  }, [oidc.user]);

  const error = oidc.error?.message ?? null;

  const login = useCallback(async () => {
    await oidc.signinRedirect();
  }, [oidc]);

  const logout = useCallback(() => {
    setApiToken(null);
    void oidc.signoutRedirect();
  }, [oidc]);

  const status: AuthStatus = oidc.isLoading
    ? "loading"
    : oidc.isAuthenticated
      ? "authenticated"
      : "unauthenticated";

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      principal: oidc.user ? profileToPrincipal(oidc.user.profile) : null,
      authMode: "oidc",
      devRoles: roles,
      error,
      login,
      logout,
    }),
    [status, oidc.user, roles, error, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

function profileToPrincipal(profile: Record<string, unknown>): Principal {
  const roles: string[] = [];
  if (Array.isArray(profile.roles)) {
    roles.push(...profile.roles.map(String));
  }
  const realmAccess = profile.realm_access;
  if (
    realmAccess &&
    typeof realmAccess === "object" &&
    Array.isArray((realmAccess as { roles?: unknown }).roles)
  ) {
    roles.push(...((realmAccess as { roles: unknown[] }).roles.map(String) ?? []));
  }
  const subject = String(profile.sub ?? "");
  const name = String(
    profile.name ?? profile.preferred_username ?? profile.email ?? subject ?? "Unknown",
  );
  return {
    subject,
    name,
    email: String(profile.email ?? ""),
    roles: [...new Set(roles)],
    org_unit_id: typeof profile.org_unit_id === "string" ? profile.org_unit_id : null,
  };
}
