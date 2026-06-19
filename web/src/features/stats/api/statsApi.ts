/**
 * Statistika API — TanStack Query uchun hook'lar.
 *
 * Endpointlar (STATS.md):
 *   GET /stats/sales     — savdo statistikasi (stats:view)
 *   GET /stats/delivery  — yetkazish statistikasi (stats:view)
 *   GET /stats/finance   — moliyaviy statistika (finance:view — courier ko'rmaydi)
 */

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type {
  SalesStatsOut,
  DeliveryStatsOut,
  FinanceStatsOut,
  StatsFilters,
} from "../types";

// ─── Query keys ────────────────────────────────────────────────────────────────

export const statsKeys = {
  all: ["stats"] as const,
  sales: (filters?: StatsFilters) =>
    [...statsKeys.all, "sales", filters ?? {}] as const,
  delivery: (filters?: StatsFilters) =>
    [...statsKeys.all, "delivery", filters ?? {}] as const,
  finance: (filters?: StatsFilters) =>
    [...statsKeys.all, "finance", filters ?? {}] as const,
};

// ─── Savdo statistikasi ────────────────────────────────────────────────────────

export function useSalesStats(filters: StatsFilters = {}) {
  const params = new URLSearchParams();
  if (filters.from) params.set("from", filters.from);
  if (filters.to) params.set("to", filters.to);
  if (filters.group_by) params.set("group_by", filters.group_by);
  if (filters.branch_id) params.set("branch_id", filters.branch_id);

  const qs = params.toString();

  return useQuery({
    queryKey: statsKeys.sales(filters),
    queryFn: () =>
      apiClient.get<SalesStatsOut>(`/stats/sales${qs ? `?${qs}` : ""}`),
    staleTime: 1000 * 60 * 5,
  });
}

// ─── Yetkazish statistikasi ────────────────────────────────────────────────────

export function useDeliveryStats(filters: StatsFilters = {}) {
  const params = new URLSearchParams();
  if (filters.from) params.set("from", filters.from);
  if (filters.to) params.set("to", filters.to);
  if (filters.courier_id) params.set("courier_id", filters.courier_id);

  const qs = params.toString();

  return useQuery({
    queryKey: statsKeys.delivery(filters),
    queryFn: () =>
      apiClient.get<DeliveryStatsOut>(`/stats/delivery${qs ? `?${qs}` : ""}`),
    staleTime: 1000 * 60 * 5,
  });
}

// ─── Moliyaviy statistika ─────────────────────────────────────────────────────

/**
 * Finance statistika — faqat finance:view ruxsati borlar uchun.
 * enabled=false bo'lsa query chaqirilmaydi (courier uchun).
 *
 * RBAC scope (STATS.md):
 *   administrator/accountant: barchasi
 *   agent/store: faqat o'z do'konlari
 *   courier: 403 — shuning uchun klient yubormasligi kerak (enabled=false)
 */
export function useFinanceStats(filters: StatsFilters = {}, enabled = true) {
  const params = new URLSearchParams();
  if (filters.from) params.set("from", filters.from);
  if (filters.to) params.set("to", filters.to);
  if (filters.branch_id) params.set("branch_id", filters.branch_id);

  const qs = params.toString();

  return useQuery({
    queryKey: statsKeys.finance(filters),
    queryFn: () =>
      apiClient.get<FinanceStatsOut>(`/stats/finance${qs ? `?${qs}` : ""}`),
    enabled,
    staleTime: 1000 * 60 * 2, // moliyaviy — qisqaroq TTL
  });
}
