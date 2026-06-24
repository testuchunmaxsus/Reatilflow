/**
 * POS API — TanStack Query hook'lari va API chaqiruvlar.
 *
 * Endpointlar (backend router.py):
 *   POST /pos/sales          — yangi sotuv (checkout), 201
 *   GET  /pos/sales          — sotuvlar ro'yxati (paginated)
 *   GET  /pos/summary        — kunlik statistika
 *   GET  /marketplace/inventory — do'kon inventari (expiry bayroqlari bilan)
 *
 * Narx xavfsizligi: klient FAQAT product_id + qty yuboradi. Narx server tomonida.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type {
  PaginatedPosSales,
  PosSale,
  PosSaleCreate,
  PosSummary,
  PaginatedPosInventory,
} from "../types";

// ─── Query keys ───────────────────────────────────────────────────────────────

export const posKeys = {
  all: ["pos"] as const,
  sales: (filters?: SalesFilters) =>
    [...posKeys.all, "sales", filters ?? {}] as const,
  summary: (date?: string, storeId?: string) =>
    [...posKeys.all, "summary", date ?? "", storeId ?? ""] as const,
  inventory: (filters?: InventoryFilters) =>
    [...posKeys.all, "inventory", filters ?? {}] as const,
};

// ─── Filtr tiplaari ───────────────────────────────────────────────────────────

export interface SalesFilters {
  store_id?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}

export interface InventoryFilters {
  store_id?: string;
  product_id?: string;
  status?: string;
  page?: number;
  limit?: number;
}

// ─── Sotuvlar ro'yxati ────────────────────────────────────────────────────────

export function usePosSales(filters: SalesFilters = {}) {
  const params = new URLSearchParams();
  if (filters.store_id) params.set("store_id", filters.store_id);
  if (filters.date_from) params.set("date_from", filters.date_from);
  if (filters.date_to) params.set("date_to", filters.date_to);
  params.set("limit", String(filters.limit ?? 20));
  params.set("offset", String(filters.offset ?? 0));
  const qs = params.toString();

  return useQuery({
    queryKey: posKeys.sales(filters),
    queryFn: () => apiClient.get<PaginatedPosSales>(`/pos/sales?${qs}`),
    placeholderData: (prev) => prev,
  });
}

// ─── Kunlik summary ───────────────────────────────────────────────────────────

export function usePosSummary(date?: string, storeId?: string) {
  const params = new URLSearchParams();
  if (date) params.set("date", date);
  if (storeId) params.set("store_id", storeId);
  const qs = params.toString();

  return useQuery({
    queryKey: posKeys.summary(date, storeId),
    queryFn: () =>
      apiClient.get<PosSummary>(`/pos/summary${qs ? `?${qs}` : ""}`),
    staleTime: 1000 * 60 * 2, // 2 daqiqa
  });
}

// ─── Yangi sotuv yaratish ─────────────────────────────────────────────────────

export function useCreatePosSale() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: PosSaleCreate) =>
      apiClient.post<PosSale>("/pos/sales", data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: posKeys.all });
    },
  });
}

// ─── Inventar (expiry bayroqlari bilan) ──────────────────────────────────────

export function usePosInventory(filters: InventoryFilters = {}) {
  const params = new URLSearchParams();
  if (filters.store_id) params.set("store_id", filters.store_id);
  if (filters.product_id) params.set("product_id", filters.product_id);
  if (filters.status) params.set("status", filters.status);
  params.set("page", String(filters.page ?? 1));
  params.set("limit", String(filters.limit ?? 50));
  const qs = params.toString();

  return useQuery({
    queryKey: posKeys.inventory(filters),
    queryFn: () =>
      apiClient.get<PaginatedPosInventory>(
        `/marketplace/inventory?${qs}`,
      ),
    placeholderData: (prev) => prev,
  });
}
