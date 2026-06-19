/**
 * Buyurtma API — TanStack Query uchun hook'lar va API chaqiruvlar.
 *
 * Endpointlar (ORDERS.md §1):
 *   GET  /orders              paginated, filter: status/store/agent/sana
 *   GET  /orders/{id}         bitta buyurtma (qatorlar bilan)
 *   POST /orders              yangi buyurtma (atomik)
 *   PATCH /orders/{id}/status holat o'zgartirish (server-avtoritar)
 *
 * T11 himoyasi: OrderLineIn faqat product_id + qty. Narx/discount klient tomonidan YUBORILMAYDI.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type {
  OrderOut,
  OrderCreate,
  OrderStatusUpdate,
  PaginatedOrders,
  OrderFilters,
} from "../types";

// ─── Query keys ───────────────────────────────────────────────────────────────

export const orderKeys = {
  all: ["orders"] as const,
  list: (filters?: OrderFilters) =>
    [...orderKeys.all, "list", filters ?? {}] as const,
  detail: (id: string) => [...orderKeys.all, "detail", id] as const,
};

// ─── Buyurtmalar ro'yxati ─────────────────────────────────────────────────────

export function useOrders(filters: OrderFilters = {}) {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.store_id) params.set("store_id", filters.store_id);
  if (filters.agent_id) params.set("agent_id", filters.agent_id);
  if (filters.from) params.set("from", filters.from);
  if (filters.to) params.set("to", filters.to);
  params.set("limit", String(filters.limit ?? 20));
  params.set("offset", String(filters.offset ?? 0));

  const qs = params.toString();

  return useQuery({
    queryKey: orderKeys.list(filters),
    queryFn: () => apiClient.get<PaginatedOrders>(`/orders?${qs}`),
    placeholderData: (prev) => prev,
  });
}

// ─── Bitta buyurtma ───────────────────────────────────────────────────────────

export function useOrder(id: string, enabled = true) {
  return useQuery({
    queryKey: orderKeys.detail(id),
    queryFn: () => apiClient.get<OrderOut>(`/orders/${id}`),
    enabled: enabled && Boolean(id),
  });
}

// ─── Buyurtma yaratish ────────────────────────────────────────────────────────

export function useCreateOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: OrderCreate) =>
      apiClient.post<OrderOut>("/orders", data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: orderKeys.all });
    },
  });
}

// ─── Holat o'zgartirish ───────────────────────────────────────────────────────

export function useUpdateOrderStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: OrderStatusUpdate }) =>
      apiClient.patch<OrderOut>(`/orders/${id}/status`, data),
    onSuccess: (updated) => {
      // Detail keshni yangilaymiz
      queryClient.setQueryData(orderKeys.detail(updated.id), updated);
      // Ro'yxat keshini invalidate qilamiz
      void queryClient.invalidateQueries({ queryKey: orderKeys.list() });
    },
  });
}
