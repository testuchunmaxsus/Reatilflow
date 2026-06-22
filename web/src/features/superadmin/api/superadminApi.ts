/**
 * Superadmin API — TanStack Query hook'lari.
 *
 * Backend endpointlari (superadmin/router.py):
 *   POST   /superadmin/enterprises          — korxona + admin yaratish
 *   GET    /superadmin/enterprises          — ro'yxat (paginated)
 *   GET    /superadmin/enterprises/{id}     — bitta korxona
 *   PATCH  /superadmin/enterprises/{id}     — yangilash
 *   PATCH  /superadmin/enterprises/{id}/suspend  — to'xtatish
 *   PATCH  /superadmin/enterprises/{id}/activate — faollashtirish
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type {
  SuperadminEnterpriseOut,
  SuperadminEnterpriseAdminOut,
  SuperadminEnterprisePaginated,
  EnterpriseCreate,
  EnterpriseUpdate,
} from "../types";

// ─── Query keys ───────────────────────────────────────────────────────────────

export const enterpriseKeys = {
  all: ["superadmin-enterprises"] as const,
  list: (limit: number, offset: number) =>
    [...enterpriseKeys.all, "list", { limit, offset }] as const,
  detail: (id: string) => [...enterpriseKeys.all, "detail", id] as const,
};

// ─── Ro'yxat ──────────────────────────────────────────────────────────────────

export function useEnterprises(limit = 20, offset = 0) {
  return useQuery({
    queryKey: enterpriseKeys.list(limit, offset),
    queryFn: () =>
      apiClient.get<SuperadminEnterprisePaginated>(
        `/superadmin/enterprises?limit=${limit}&offset=${offset}`,
      ),
    placeholderData: (prev) => prev,
  });
}

// ─── Bitta korxona ────────────────────────────────────────────────────────────

export function useEnterprise(id: string, enabled = true) {
  return useQuery({
    queryKey: enterpriseKeys.detail(id),
    queryFn: () =>
      apiClient.get<SuperadminEnterpriseOut>(`/superadmin/enterprises/${id}`),
    enabled,
  });
}

// ─── Yaratish ─────────────────────────────────────────────────────────────────

export function useCreateEnterprise() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: EnterpriseCreate) =>
      apiClient.post<SuperadminEnterpriseAdminOut>("/superadmin/enterprises", data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: enterpriseKeys.all });
    },
  });
}

// ─── Yangilash ────────────────────────────────────────────────────────────────

export function useUpdateEnterprise() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: EnterpriseUpdate }) =>
      apiClient.patch<SuperadminEnterpriseOut>(`/superadmin/enterprises/${id}`, data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: enterpriseKeys.all });
    },
  });
}

// ─── Suspend ──────────────────────────────────────────────────────────────────

export function useSuspendEnterprise() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiClient.patch<SuperadminEnterpriseOut>(`/superadmin/enterprises/${id}/suspend`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: enterpriseKeys.all });
    },
  });
}

// ─── Activate ─────────────────────────────────────────────────────────────────

export function useActivateEnterprise() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiClient.patch<SuperadminEnterpriseOut>(`/superadmin/enterprises/${id}/activate`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: enterpriseKeys.all });
    },
  });
}
