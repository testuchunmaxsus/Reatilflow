/**
 * Superadmin API — TanStack Query hook'lari.
 *
 * Backend endpointlari (superadmin/router.py):
 *   GET    /superadmin/stats                       — dashboard statistika
 *   POST   /superadmin/enterprises                 — korxona + admin yaratish
 *   GET    /superadmin/enterprises                 — ro'yxat (paginated, search, status)
 *   GET    /superadmin/enterprises/{id}            — tafsilot + adminlar
 *   PATCH  /superadmin/enterprises/{id}            — yangilash
 *   PATCH  /superadmin/enterprises/{id}/suspend    — to'xtatish
 *   PATCH  /superadmin/enterprises/{id}/activate   — faollashtirish
 *   DELETE /superadmin/enterprises/{id}            — soft-delete
 *   POST   /superadmin/enterprises/{id}/reset-admin-password — parol reset
 *   GET    /superadmin/users                       — cross-tenant foydalanuvchilar
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type {
  SuperadminEnterpriseOut,
  SuperadminEnterpriseAdminOut,
  SuperadminEnterprisePaginated,
  SuperadminEnterpriseDetail,
  SuperadminStats,
  SuperadminUserPaginated,
  ResetAdminPasswordRequest,
  ResetAdminPasswordResponse,
  EnterpriseCreate,
  EnterpriseUpdate,
  EnterpriseListFilters,
  AuditLogPaginated,
  AuditLogFilters,
  SuperadminBannerPaginated,
  SuperadminBannerFilters,
} from "../types";

// ─── Query keys ───────────────────────────────────────────────────────────────

export const enterpriseKeys = {
  all: ["superadmin-enterprises"] as const,
  list: (filters: EnterpriseListFilters) =>
    [...enterpriseKeys.all, "list", filters] as const,
  detail: (id: string) => [...enterpriseKeys.all, "detail", id] as const,
  stats: ["superadmin-stats"] as const,
  users: (filters: Record<string, unknown>) =>
    ["superadmin-users", filters] as const,
};

// ─── Dashboard statistika ─────────────────────────────────────────────────────

export function useSuperadminStats() {
  return useQuery({
    queryKey: enterpriseKeys.stats,
    queryFn: () => apiClient.get<SuperadminStats>("/superadmin/stats"),
  });
}

// ─── Ro'yxat (search + status filter) ────────────────────────────────────────

export function useEnterprises(filters: EnterpriseListFilters = {}) {
  const { search = "", status = "", limit = 20, offset = 0 } = filters;
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (status) params.set("status", status);
  params.set("limit", String(limit));
  params.set("offset", String(offset));

  return useQuery({
    queryKey: enterpriseKeys.list(filters),
    queryFn: () =>
      apiClient.get<SuperadminEnterprisePaginated>(
        `/superadmin/enterprises?${params.toString()}`,
      ),
    placeholderData: (prev) => prev,
  });
}

// ─── Korxona tafsiloti ────────────────────────────────────────────────────────

export function useEnterpriseDetail(id: string, enabled = true) {
  return useQuery({
    queryKey: enterpriseKeys.detail(id),
    queryFn: () =>
      apiClient.get<SuperadminEnterpriseDetail>(`/superadmin/enterprises/${id}`),
    enabled: !!id && enabled,
  });
}

/** Eski nomi saqlanadi — mavjud kodga mos (EnterpriseFormModal ishlatadi) */
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
      void queryClient.invalidateQueries({ queryKey: enterpriseKeys.stats });
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
      void queryClient.invalidateQueries({ queryKey: enterpriseKeys.stats });
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
      void queryClient.invalidateQueries({ queryKey: enterpriseKeys.stats });
    },
  });
}

// ─── O'chirish (soft-delete) ──────────────────────────────────────────────────

export function useDeleteEnterprise() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiClient.delete<void>(`/superadmin/enterprises/${id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: enterpriseKeys.all });
      void queryClient.invalidateQueries({ queryKey: enterpriseKeys.stats });
    },
  });
}

// ─── Parol reset ──────────────────────────────────────────────────────────────

export function useResetAdminPassword(enterpriseId: string) {
  return useMutation({
    mutationFn: (body: ResetAdminPasswordRequest) =>
      apiClient.post<ResetAdminPasswordResponse>(
        `/superadmin/enterprises/${enterpriseId}/reset-admin-password`,
        body,
      ),
  });
}

// ─── Audit log ────────────────────────────────────────────────────────────────

export const auditLogKeys = {
  all: ["superadmin-audit-logs"] as const,
  list: (filters: AuditLogFilters) =>
    [...auditLogKeys.all, "list", filters] as const,
};

export function useAuditLogs(filters: AuditLogFilters = {}) {
  const { action = "", entity_type = "", entity_id = "", enterprise_id = "", limit = 20, offset = 0 } = filters;
  const params = new URLSearchParams();
  if (action) params.set("action", action);
  if (entity_type) params.set("entity_type", entity_type);
  if (entity_id) params.set("entity_id", entity_id);
  if (enterprise_id) params.set("enterprise_id", enterprise_id);
  params.set("limit", String(limit));
  params.set("offset", String(offset));

  return useQuery({
    queryKey: auditLogKeys.list(filters),
    queryFn: () =>
      apiClient.get<AuditLogPaginated>(
        `/superadmin/audit-logs?${params.toString()}`,
      ),
    placeholderData: (prev) => prev,
  });
}

// ─── Superadmin bannerlar ─────────────────────────────────────────────────────

export const superadminBannerKeys = {
  all: ["superadmin-banners"] as const,
  list: (filters: SuperadminBannerFilters) =>
    [...superadminBannerKeys.all, "list", filters] as const,
};

export function useSuperadminBanners(filters: SuperadminBannerFilters = {}) {
  const { enterprise_id = "", is_active = null, limit = 20, offset = 0 } = filters;
  const params = new URLSearchParams();
  if (enterprise_id) params.set("enterprise_id", enterprise_id);
  if (is_active !== null && is_active !== undefined) params.set("is_active", String(is_active));
  params.set("limit", String(limit));
  params.set("offset", String(offset));

  return useQuery({
    queryKey: superadminBannerKeys.list(filters),
    queryFn: () =>
      apiClient.get<SuperadminBannerPaginated>(
        `/superadmin/banners?${params.toString()}`,
      ),
    placeholderData: (prev) => prev,
  });
}

export function useToggleBannerActive() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      apiClient.patch<void>(`/marketplace/banners/${id}`, { is_active }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: superadminBannerKeys.all });
    },
  });
}

export function useDeleteBanner() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiClient.delete<void>(`/marketplace/banners/${id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: superadminBannerKeys.all });
    },
  });
}

// ─── Cross-tenant foydalanuvchilar ────────────────────────────────────────────

export interface SuperadminUsersFilters {
  enterprise_id?: string;
  role?: string;
  limit?: number;
  offset?: number;
}

export function useSuperadminUsers(filters: SuperadminUsersFilters = {}) {
  const { enterprise_id = "", role = "", limit = 20, offset = 0 } = filters;
  const params = new URLSearchParams();
  if (enterprise_id) params.set("enterprise_id", enterprise_id);
  if (role) params.set("role", role);
  params.set("limit", String(limit));
  params.set("offset", String(offset));

  return useQuery({
    queryKey: enterpriseKeys.users(filters as Record<string, unknown>),
    queryFn: () =>
      apiClient.get<SuperadminUserPaginated>(
        `/superadmin/users?${params.toString()}`,
      ),
    placeholderData: (prev) => prev,
  });
}
