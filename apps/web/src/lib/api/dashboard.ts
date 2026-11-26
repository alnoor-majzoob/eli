/* eslint-disable @typescript-eslint/no-explicit-any */
import { api } from "@/lib/api";

type AnyData = any;

export async function getDashboard() {
  const { data } = await api.GET("/api/v1/dashboard" as any, {});
  return (data ?? {}) as AnyData;
}
