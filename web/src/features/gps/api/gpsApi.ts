/**
 * GPS API — TanStack Query hook'lari.
 *
 * Endpointlar:
 *   GET /gps/track?user_id=&date=&limit=&offset=  — foydalanuvchi+sana marshrut
 *   GET /gps/track/{delivery_id}                  — yetkazish marshrutini ko'rish
 *
 * RBAC:
 *   gps:view — agent/courier (faqat o'ziniki), administrator (barchasi).
 */

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type { GpsTrackFilters, PaginatedTrack } from "../types";

// ─── Query keys ───────────────────────────────────────────────────────────────

export const gpsKeys = {
  all: ["gps"] as const,
  track: (filters?: GpsTrackFilters) =>
    [...gpsKeys.all, "track", filters ?? {}] as const,
  trackByDelivery: (deliveryId: string) =>
    [...gpsKeys.all, "track-delivery", deliveryId] as const,
};

// ─── Foydalanuvchi+sana bo'yicha marshrut ────────────────────────────────────

export function useGpsTrack(filters: GpsTrackFilters = {}) {
  const params = new URLSearchParams();
  if (filters.user_id) params.set("user_id", filters.user_id);
  if (filters.date) params.set("date", filters.date);
  params.set("limit", String(filters.limit ?? 200));
  params.set("offset", String(filters.offset ?? 0));
  const qs = params.toString();

  return useQuery({
    queryKey: gpsKeys.track(filters),
    queryFn: () => apiClient.get<PaginatedTrack>(`/gps/track?${qs}`),
    placeholderData: (prev) => prev,
  });
}

// ─── Yetkazish bo'yicha marshrut ─────────────────────────────────────────────

export function useGpsTrackByDelivery(
  deliveryId: string,
  options: { limit?: number; offset?: number } = {},
) {
  const params = new URLSearchParams();
  params.set("limit", String(options.limit ?? 200));
  params.set("offset", String(options.offset ?? 0));
  const qs = params.toString();

  return useQuery({
    queryKey: gpsKeys.trackByDelivery(deliveryId),
    queryFn: () =>
      apiClient.get<PaginatedTrack>(`/gps/track/${deliveryId}?${qs}`),
    enabled: Boolean(deliveryId),
    placeholderData: (prev) => prev,
  });
}
