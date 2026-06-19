/**
 * Foydalanuvchilar API — TanStack Query hook'lari va API chaqiruvlar.
 *
 * Backend endpointlari (users/router.py):
 *   GET    /users              — paginated ro'yxat (filter: role, branch_id, is_active)
 *   POST   /users              — yaratish (admin only)
 *   GET    /users/{id}         — bitta foydalanuvchi
 *   PATCH  /users/{id}         — yangilash (version optimistik lock)
 *   PATCH  /users/{id}/deactivate — deaktivatsiya
 *   PATCH  /users/{id}/activate   — qayta aktivlashtirish
 *
 * Do'konlar ro'yxati (agent biriktirish uchun):
 *   GET    /customers/stores   — mavjud do'konlar (id + name)
 *   POST   /customers/stores/{id}/assign-agent — agentni do'konga biriktirish
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type { UserOut, PaginatedUsers, UserCreate, UserUpdate, UserFilters } from "../types";
import type { PaginatedStores } from "@/features/customers/types";

// ─── Query keys ───────────────────────────────────────────────────────────────

export const userKeys = {
  all: ["users"] as const,
  list: (filters?: UserFilters) => [...userKeys.all, "list", filters ?? {}] as const,
  detail: (id: string) => [...userKeys.all, "detail", id] as const,
};

// ─── Ro'yxat ──────────────────────────────────────────────────────────────────

export function useUsers(filters: UserFilters = {}) {
  const params = new URLSearchParams();
  if (filters.role) params.set("role", filters.role);
  if (filters.branch_id) params.set("branch_id", filters.branch_id);
  if (filters.is_active !== undefined)
    params.set("is_active", String(filters.is_active));
  params.set("limit", String(filters.limit ?? 20));
  params.set("offset", String(filters.offset ?? 0));

  const qs = params.toString();

  return useQuery({
    queryKey: userKeys.list(filters),
    queryFn: () => apiClient.get<PaginatedUsers>(`/users?${qs}`),
    placeholderData: (prev) => prev,
  });
}

// ─── Bitta foydalanuvchi ──────────────────────────────────────────────────────

export function useUser(id: string, enabled = true) {
  return useQuery({
    queryKey: userKeys.detail(id),
    queryFn: () => apiClient.get<UserOut>(`/users/${id}`),
    enabled,
  });
}

// ─── Yaratish ─────────────────────────────────────────────────────────────────

export function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: UserCreate) => apiClient.post<UserOut>("/users", data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: userKeys.all });
    },
  });
}

// ─── Yangilash (PATCH) ────────────────────────────────────────────────────────

export function useUpdateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UserUpdate }) =>
      apiClient.patch<UserOut>(`/users/${id}`, data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: userKeys.all });
    },
  });
}

// ─── Deaktivatsiya ────────────────────────────────────────────────────────────

export function useDeactivateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiClient.patch<UserOut>(`/users/${id}/deactivate`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: userKeys.all });
    },
  });
}

// ─── Aktivlashtirish ──────────────────────────────────────────────────────────
// Backend PATCH /users/{id}/activate (deactivate teskarisi, is_active=True).

export function useActivateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiClient.patch<UserOut>(`/users/${id}/activate`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: userKeys.all });
    },
  });
}

// ─── Do'konlar ro'yxati (agent biriktirish uchun) ─────────────────────────────

export function useStoreOptions() {
  return useQuery({
    queryKey: ["stores-for-assign"],
    queryFn: () =>
      apiClient.get<PaginatedStores>("/customers/stores?limit=200&offset=0"),
    staleTime: 1000 * 60 * 2, // 2 daqiqa
  });
}

// ─── Agent→do'kon biriktirish ─────────────────────────────────────────────────

export function useAssignAgentToStore() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ storeId, agentId }: { storeId: string; agentId: string }) =>
      apiClient.post<{ store_id: string; agent_id: string; assigned_at: string }>(
        `/customers/stores/${storeId}/assign-agent`,
        { agent_id: agentId },
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["stores-for-assign"] });
      void queryClient.invalidateQueries({ queryKey: userKeys.all });
    },
  });
}
