/* eslint-disable @typescript-eslint/no-explicit-any */
import { api } from "@/lib/api";

export interface UserRead {
  id: string;
  subject: string;
  name: string;
  email: string;
  org_unit_id: string | null;
  roles: string[];
}

export async function listUsers(): Promise<UserRead[]> {
  const { data } = await api.GET("/api/v1/users" as any, {});
  return (data ?? []) as UserRead[];
}
