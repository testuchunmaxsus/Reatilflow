/**
 * Mijoz bazasi API — TanStack Query uchun hook'lar va API chaqiruvlar.
 *
 * Endpointlar (CUSTOMERS.md §1):
 *   GET  /customers/stores          paginated, blind-index qidiruv
 *   POST /customers/stores
 *   PATCH /customers/stores/{id}
 *   DELETE /customers/stores/{id}
 *   POST /customers/stores/{id}/assign-agent  (admin only)
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type { StoreOut } from "@/api/types";
import type {
  AssignAgentRequest,
  AssignAgentResponse,
  PaginatedStores,
  StoreCreate,
  StoreFilters,
  StoreUpdate,
} from "../types";

// ─── Query keys ──────────────────────────────────────────────────────────────

export const customerKeys = {
  all: ["customers"] as const,
  stores: (filters?: StoreFilters) =>
    [...customerKeys.all, "stores", filters ?? {}] as const,
  store: (id: string) => [...customerKeys.all, "store", id] as const,
};

// ─── Do'konlar ro'yxati ───────────────────────────────────────────────────────

export function useStores(filters: StoreFilters = {}) {
  const params = new URLSearchParams();
  if (filters.search_name) params.set("search_name", filters.search_name);
  if (filters.search_inn) params.set("search_inn", filters.search_inn);
  if (filters.search_phone) params.set("search_phone", filters.search_phone);
  params.set("limit", String(filters.limit ?? 20));
  params.set("offset", String(filters.offset ?? 0));

  const qs = params.toString();

  return useQuery({
    queryKey: customerKeys.stores(filters),
    queryFn: () => apiClient.get<PaginatedStores>(`/customers/stores?${qs}`),
    placeholderData: (prev) => prev,
  });
}

// ─── Do'kon yaratish ──────────────────────────────────────────────────────────

export function useCreateStore() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: StoreCreate) =>
      apiClient.post<StoreOut>("/customers/stores", data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: customerKeys.all });
    },
  });
}

// ─── Do'kon tahrirlash ────────────────────────────────────────────────────────

export function useUpdateStore() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: StoreUpdate }) =>
      apiClient.patch<StoreOut>(`/customers/stores/${id}`, data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: customerKeys.all });
    },
  });
}

// ─── Do'kon o'chirish ─────────────────────────────────────────────────────────

export function useDeleteStore() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiClient.delete<void>(`/customers/stores/${id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: customerKeys.all });
    },
  });
}

// ─── Agent biriktirish (admin only) ──────────────────────────────────────────

export function useAssignAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      storeId,
      data,
    }: {
      storeId: string;
      data: AssignAgentRequest;
    }) =>
      apiClient.post<AssignAgentResponse>(
        `/customers/stores/${storeId}/assign-agent`,
        data,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: customerKeys.all });
    },
  });
}
