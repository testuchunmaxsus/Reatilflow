/**
 * Analytics API — TanStack Query hook'lar.
 *
 * Endpointlar (ADR-004):
 *   GET /analytics/overview         — KPI kartalar
 *   GET /analytics/stores           — Shartnoma qilgan do'konlar
 *   GET /analytics/geo-velocity     — Geo savdo tezligi
 *   GET /analytics/expiry           — Muddati o'tgan/o'tayotgan partiyalar
 *   GET /analytics/products         — Mahsulot reytingi
 *   GET /analytics/recommendations  — AI tavsiyalar
 *
 * Barchasi analytics:view ruxsatini talab qiladi (backend tekshiradi).
 */

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type {
  OverviewOut,
  ContractedStoresOut,
  GeoVelocityOut,
  ExpiryReportOut,
  ProductRankingOut,
  RecommendationsOut,
  AnalyticsFilters,
  ProductOrder,
} from "../types";

// ─── Query keys ────────────────────────────────────────────────────────────────

export const analyticsKeys = {
  all: ["analytics"] as const,
  overview: (filters?: AnalyticsFilters) =>
    [...analyticsKeys.all, "overview", filters ?? {}] as const,
  stores: () => [...analyticsKeys.all, "stores"] as const,
  geoVelocity: (filters?: AnalyticsFilters) =>
    [...analyticsKeys.all, "geo-velocity", filters ?? {}] as const,
  expiry: (withinDays?: number) =>
    [...analyticsKeys.all, "expiry", withinDays ?? 30] as const,
  products: (filters?: AnalyticsFilters, order?: ProductOrder, limit?: number) =>
    [...analyticsKeys.all, "products", filters ?? {}, order ?? "top", limit ?? 10] as const,
  recommendations: () => [...analyticsKeys.all, "recommendations"] as const,
};

// ─── Overview ─────────────────────────────────────────────────────────────────

export function useOverview(filters: AnalyticsFilters = {}) {
  const params = new URLSearchParams();
  if (filters.from) params.set("from", filters.from);
  if (filters.to) params.set("to", filters.to);
  const qs = params.toString();

  return useQuery({
    queryKey: analyticsKeys.overview(filters),
    queryFn: () =>
      apiClient.get<OverviewOut>(`/analytics/overview${qs ? `?${qs}` : ""}`),
    staleTime: 1000 * 60 * 5,
  });
}

// ─── Contracted stores ─────────────────────────────────────────────────────────

export function useContractedStores() {
  return useQuery({
    queryKey: analyticsKeys.stores(),
    queryFn: () => apiClient.get<ContractedStoresOut>("/analytics/stores"),
    staleTime: 1000 * 60 * 5,
  });
}

// ─── Geo velocity ──────────────────────────────────────────────────────────────

export function useGeoVelocity(filters: AnalyticsFilters = {}) {
  const params = new URLSearchParams();
  if (filters.from) params.set("from", filters.from);
  if (filters.to) params.set("to", filters.to);
  const qs = params.toString();

  return useQuery({
    queryKey: analyticsKeys.geoVelocity(filters),
    queryFn: () =>
      apiClient.get<GeoVelocityOut>(`/analytics/geo-velocity${qs ? `?${qs}` : ""}`),
    staleTime: 1000 * 60 * 5,
  });
}

// ─── Expiry report ─────────────────────────────────────────────────────────────

export function useExpiry(withinDays = 30) {
  return useQuery({
    queryKey: analyticsKeys.expiry(withinDays),
    queryFn: () =>
      apiClient.get<ExpiryReportOut>(`/analytics/expiry?within_days=${withinDays}`),
    staleTime: 1000 * 60 * 3,
  });
}

// ─── Product ranking ───────────────────────────────────────────────────────────

export function useProductRanking(
  filters: AnalyticsFilters = {},
  order: ProductOrder = "top",
  limit = 10,
) {
  const params = new URLSearchParams();
  if (filters.from) params.set("from", filters.from);
  if (filters.to) params.set("to", filters.to);
  params.set("order", order);
  params.set("limit", String(limit));

  return useQuery({
    queryKey: analyticsKeys.products(filters, order, limit),
    queryFn: () =>
      apiClient.get<ProductRankingOut>(`/analytics/products?${params.toString()}`),
    staleTime: 1000 * 60 * 5,
  });
}

// ─── Recommendations ──────────────────────────────────────────────────────────

export function useRecommendations() {
  return useQuery({
    queryKey: analyticsKeys.recommendations(),
    queryFn: () => apiClient.get<RecommendationsOut>("/analytics/recommendations"),
    staleTime: 1000 * 60 * 10, // tavsiyalar — uzunroq TTL
  });
}
