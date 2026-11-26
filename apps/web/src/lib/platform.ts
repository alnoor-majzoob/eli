import { useQuery } from "@tanstack/react-query";

import { api, problemMessage } from "./api";
import type { Health, PlatformConfig, Readiness } from "./api-types";

export function usePlatformConfig() {
  return useQuery({
    queryKey: ["platform-config"],
    queryFn: async (): Promise<PlatformConfig> => {
      const { data, error, response } = await api.GET("/api/v1/platform/config");
      if (!response.ok || !data) {
        throw new Error(problemMessage(error, "Unable to load platform configuration."));
      }
      return data;
    },
    staleTime: 60_000,
  });
}

export function useHealth() {
  return useQuery({
    queryKey: ["healthz"],
    queryFn: async (): Promise<Health> => {
      const { data, response } = await api.GET("/healthz");
      if (!response.ok || !data) {
        throw new Error("API health check failed.");
      }
      return data as unknown as Health;
    },
    refetchInterval: 30_000,
  });
}

export function useReadiness() {
  return useQuery({
    queryKey: ["readyz"],
    queryFn: async (): Promise<Readiness> => {
      const { data } = await api.GET("/readyz");
      if (!data) {
        throw new Error("Readiness check failed.");
      }
      return data as unknown as Readiness;
    },
    refetchInterval: 30_000,
  });
}
