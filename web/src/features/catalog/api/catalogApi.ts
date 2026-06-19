/**
 * Katalog API — TanStack Query uchun hook'lar va API chaqiruvlar.
 *
 * Endpointlar (CATALOG.md §1.3):
 *   GET  /catalog/categories
 *   GET  /catalog/price-segments
 *   GET  /catalog/products         paginated, qidiruv, filter
 *   POST /catalog/products
 *   PATCH /catalog/products/{id}
 *   DELETE /catalog/products/{id}
 *   GET  /catalog/products/{id}/price-history
 *   POST /catalog/products/{id}/photo
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type {
  CategoryOut,
  PriceSegmentOut,
  ProductOut,
  PriceHistoryOut,
} from "@/api/types";
import type {
  PaginatedProducts,
  ProductCreate,
  ProductUpdate,
} from "../types";

// ─── Query keys ──────────────────────────────────────────────────────────────

export const catalogKeys = {
  all: ["catalog"] as const,
  categories: () => [...catalogKeys.all, "categories"] as const,
  segments: () => [...catalogKeys.all, "segments"] as const,
  products: (filters?: ProductFilters) =>
    [...catalogKeys.all, "products", filters ?? {}] as const,
  priceHistory: (id: string) =>
    [...catalogKeys.all, "priceHistory", id] as const,
};

// ─── Filtr tipi ──────────────────────────────────────────────────────────────

export interface ProductFilters {
  search?: string;
  is_active?: boolean | null;
  category_id?: string | null;
  limit?: number;
  offset?: number;
}

// ─── Kategoriyalar ────────────────────────────────────────────────────────────

export function useCategories() {
  return useQuery({
    queryKey: catalogKeys.categories(),
    queryFn: () => apiClient.get<CategoryOut[]>("/catalog/categories"),
    staleTime: 1000 * 60 * 10, // 10 daqiqa
  });
}

// ─── Narx segmentlari ─────────────────────────────────────────────────────────

export function usePriceSegments() {
  return useQuery({
    queryKey: catalogKeys.segments(),
    queryFn: () => apiClient.get<PriceSegmentOut[]>("/catalog/price-segments"),
    staleTime: 1000 * 60 * 10,
  });
}

// ─── Mahsulotlar ro'yxati ─────────────────────────────────────────────────────

export function useProducts(filters: ProductFilters = {}) {
  const params = new URLSearchParams();
  if (filters.search) params.set("search", filters.search);
  if (filters.is_active !== undefined && filters.is_active !== null) {
    params.set("is_active", String(filters.is_active));
  }
  if (filters.category_id) params.set("category_id", filters.category_id);
  params.set("limit", String(filters.limit ?? 20));
  params.set("offset", String(filters.offset ?? 0));

  const qs = params.toString();

  return useQuery({
    queryKey: catalogKeys.products(filters),
    queryFn: () =>
      apiClient.get<PaginatedProducts>(`/catalog/products?${qs}`),
    placeholderData: (prev) => prev,
  });
}

// ─── Narx tarixi ─────────────────────────────────────────────────────────────

export function usePriceHistory(productId: string, enabled = true) {
  return useQuery({
    queryKey: catalogKeys.priceHistory(productId),
    queryFn: () =>
      apiClient.get<PriceHistoryOut[]>(
        `/catalog/products/${productId}/price-history`,
      ),
    enabled: enabled && Boolean(productId),
  });
}

// ─── Mahsulot yaratish ────────────────────────────────────────────────────────

export function useCreateProduct() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: ProductCreate) =>
      apiClient.post<ProductOut>("/catalog/products", data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: catalogKeys.all });
    },
  });
}

// ─── Mahsulot tahrirlash ──────────────────────────────────────────────────────

export function useUpdateProduct() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ProductUpdate }) =>
      apiClient.patch<ProductOut>(`/catalog/products/${id}`, data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: catalogKeys.all });
    },
  });
}

// ─── Mahsulot o'chirish ───────────────────────────────────────────────────────

export function useDeleteProduct() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiClient.delete<void>(`/catalog/products/${id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: catalogKeys.all });
    },
  });
}

// ─── Rasm yuklash ─────────────────────────────────────────────────────────────
// apiClient.upload multipart/form-data uchun ishlatiladi:
// - Content-Type qo'shilmaydi (brauzer boundary bilan o'zi belgilaydi)
// - Authorization, Accept-Language va 401→refresh oqimi meros olinadi

export function useUploadPhoto() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, file }: { id: string; file: File }) => {
      const formData = new FormData();
      formData.append("file", file);
      return apiClient.upload<ProductOut>(
        `/catalog/products/${id}/photo`,
        formData,
      );
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: catalogKeys.all });
    },
  });
}
