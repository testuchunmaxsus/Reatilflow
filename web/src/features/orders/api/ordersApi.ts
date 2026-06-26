/**
 * Buyurtma API — TanStack Query uchun hook'lar va API chaqiruvlar.
 *
 * Endpointlar (ORDERS.md §1):
 *   GET    /orders                       paginated, filter: status/store/agent/sana
 *   GET    /orders/{id}                  bitta buyurtma (qatorlar bilan)
 *   POST   /orders                       yangi buyurtma (atomik)
 *   PATCH  /orders/{id}/status           holat o'zgartirish (server-avtoritar)
 *   GET    /orders/templates             shablonlar ro'yxati
 *   POST   /orders/templates             shablon yaratish
 *   DELETE /orders/templates/{id}        shablon o'chirish
 *   POST   /orders/templates/{id}/apply  shablondan buyurtma
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
  OrderTemplateOut,
  OrderTemplateCreate,
  OrderTemplateApplyOut,
} from "../types";

// ─── Query keys ───────────────────────────────────────────────────────────────

export const orderKeys = {
  all: ["orders"] as const,
  list: (filters?: OrderFilters) =>
    [...orderKeys.all, "list", filters ?? {}] as const,
  detail: (id: string) => [...orderKeys.all, "detail", id] as const,
  templates: () => [...orderKeys.all, "templates"] as const,
};

// ─── Buyurtmalar ro'yxati ─────────────────────────────────────────────────────

export function useOrders(filters: OrderFilters = {}) {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.store_id) params.set("store_id", filters.store_id);
  if (filters.agent_id) params.set("agent_id", filters.agent_id);
  // BUG FIX: backend date_from/date_to kutadi, from/to emas
  if (filters.from) params.set("date_from", filters.from);
  if (filters.to) params.set("date_to", filters.to);
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

// ─── Buyurtma shablonlari ─────────────────────────────────────────────────────

/** Shablonlar ro'yxati */
export function useTemplates() {
  return useQuery({
    queryKey: orderKeys.templates(),
    queryFn: () => apiClient.get<OrderTemplateOut[]>("/orders/templates"),
  });
}

/** Shablon yaratish */
export function useCreateTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: OrderTemplateCreate) =>
      apiClient.post<OrderTemplateOut>("/orders/templates", data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: orderKeys.templates() });
    },
  });
}

/** Shablon o'chirish */
export function useDeleteTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiClient.delete<void>(`/orders/templates/${id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: orderKeys.templates() });
    },
  });
}

/** Shablondan buyurtma yaratish */
export function useApplyTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiClient.post<OrderTemplateApplyOut>(`/orders/templates/${id}/apply`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: orderKeys.all });
    },
  });
}
