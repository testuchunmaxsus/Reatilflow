/**
 * Promo (Aksiya) API — TanStack Query hook'lari va API chaqiruvlar.
 *
 * Backend endpointlari (promo/router.py):
 *   GET    /promos          — paginated ro'yxat
 *   GET    /promos/active   — aktiv aksiyalar
 *   POST   /promos          — yaratish (faqat administrator)
 *   GET    /promos/{id}     — bitta aksiya
 *   PATCH  /promos/{id}     — yangilash (version optimistik lock)
 *   POST   /promos/{id}/banner — banner yuklash
 *   DELETE /promos/{id}     — soft-delete (faqat administrator)
 *
 * SERVER-AVTORITAR: discount server tomonda hisoblanadi; klient faqat rule kiritadi.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type {
  PromoOut,
  PaginatedPromos,
  PromoCreate,
  PromoUpdate,
  PromoFilters,
} from "../types";

// ─── Query keys ───────────────────────────────────────────────────────────────

export const promoKeys = {
  all: ["promos"] as const,
  list: (filters?: PromoFilters) =>
    [...promoKeys.all, "list", filters ?? {}] as const,
  active: () => [...promoKeys.all, "active"] as const,
  detail: (id: string) => [...promoKeys.all, "detail", id] as const,
};

// ─── Ro'yxat ──────────────────────────────────────────────────────────────────

export function usePromos(filters: PromoFilters = {}) {
  const params = new URLSearchParams();
  if (filters.is_active !== undefined)
    params.set("is_active", String(filters.is_active));
  if (filters.target_segment_id)
    params.set("target_segment_id", filters.target_segment_id);
  if (filters.target_product_id)
    params.set("target_product_id", filters.target_product_id);
  if (filters.promo_type) params.set("promo_type", filters.promo_type);
  params.set("limit", String(filters.limit ?? 20));
  params.set("offset", String(filters.offset ?? 0));

  const qs = params.toString();

  return useQuery({
    queryKey: promoKeys.list(filters),
    queryFn: () => apiClient.get<PaginatedPromos>(`/promos?${qs}`),
    placeholderData: (prev) => prev,
  });
}

// ─── Aktiv aksiyalar ──────────────────────────────────────────────────────────

export function useActivePromos() {
  return useQuery({
    queryKey: promoKeys.active(),
    queryFn: () => apiClient.get<PromoOut[]>("/promos/active"),
    staleTime: 1000 * 60 * 5,
  });
}

// ─── Bitta aksiya ─────────────────────────────────────────────────────────────

export function usePromo(id: string, enabled = true) {
  return useQuery({
    queryKey: promoKeys.detail(id),
    queryFn: () => apiClient.get<PromoOut>(`/promos/${id}`),
    enabled,
  });
}

// ─── Yaratish ─────────────────────────────────────────────────────────────────

export function useCreatePromo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: PromoCreate) =>
      apiClient.post<PromoOut>("/promos", data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: promoKeys.all });
    },
  });
}

// ─── Yangilash (PATCH) ────────────────────────────────────────────────────────

export function useUpdatePromo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: PromoUpdate }) =>
      apiClient.patch<PromoOut>(`/promos/${id}`, data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: promoKeys.all });
    },
  });
}

// ─── Banner yuklash ───────────────────────────────────────────────────────────

export function useUploadPromoBanner() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, file }: { id: string; file: File }) => {
      const formData = new FormData();
      formData.append("file", file);
      return apiClient.upload<PromoOut>(`/promos/${id}/banner`, formData);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: promoKeys.all });
    },
  });
}

// ─── O'chirish (soft-delete) ──────────────────────────────────────────────────

export function useDeletePromo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiClient.delete<void>(`/promos/${id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: promoKeys.all });
    },
  });
}

// ─── Segmentlar ro'yxati (Select uchun) ──────────────────────────────────────
// /catalog/price-segments — array qaytaradi (paginated emas)

export function useSegmentOptions() {
  return useQuery({
    queryKey: ["segments-for-select"],
    queryFn: () =>
      apiClient.get<{ id: string; name: string }[]>(
        "/catalog/price-segments",
      ),
    staleTime: 1000 * 60 * 5,
  });
}

// ─── Mahsulotlar ro'yxati (Select uchun) ─────────────────────────────────────
// /catalog/products — PaginatedProducts qaytaradi (items: ProductOut[])

export function useProductOptions() {
  return useQuery({
    queryKey: ["products-for-select"],
    queryFn: () =>
      apiClient.get<{
        items: { id: string; name_uz: string; name_ru: string }[];
      }>("/catalog/products?limit=200&offset=0&is_active=true"),
    staleTime: 1000 * 60 * 5,
  });
}
