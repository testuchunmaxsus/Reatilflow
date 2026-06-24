/**
 * Delivery API — TanStack Query hook'lari va API chaqiruvlar.
 *
 * Endpointlar:
 *   POST   /delivery                    — kuryer tayinlash (delivery:create)
 *   PATCH  /delivery/{id}/status        — holat o'zgartirish (delivery:edit)
 *   POST   /delivery/{id}/proof-photo   — isbot rasm yuklash (delivery:edit)
 *   GET    /delivery                    — ro'yxat (delivery:view, RBAC scope)
 *   GET    /delivery/{id}               — bitta yetkazish (delivery:view)
 *   GET    /marketplace/orders/deliveries — kuryer marketplace yetkazishlari
 *   POST   /marketplace/orders/{id}/proof-photo — marketplace isbot rasm
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type {
  Delivery,
  PaginatedDeliveries,
  DeliveryCreate,
  DeliveryStatusUpdate,
  DeliveryFilters,
} from "../types";
import type { IncomingOrder, PaginatedIncomingOrders } from "@/features/marketplace/types";

// ─── Query keys ───────────────────────────────────────────────────────────────

export const deliveryKeys = {
  all: ["delivery"] as const,
  list: (filters?: DeliveryFilters) =>
    [...deliveryKeys.all, "list", filters ?? {}] as const,
  detail: (id: string) => [...deliveryKeys.all, "detail", id] as const,
  courierDeliveries: (filters?: { limit?: number; offset?: number }) =>
    [...deliveryKeys.all, "marketplace-courier", filters ?? {}] as const,
};

// ─── Ro'yxat (RBAC scope bilan) ──────────────────────────────────────────────

export function useDeliveries(filters: DeliveryFilters = {}) {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.courier_id) params.set("courier_id", filters.courier_id);
  if (filters.order_id) params.set("order_id", filters.order_id);
  if (filters.date_from) params.set("date_from", filters.date_from);
  if (filters.date_to) params.set("date_to", filters.date_to);
  params.set("limit", String(filters.limit ?? 20));
  params.set("offset", String(filters.offset ?? 0));
  const qs = params.toString();

  return useQuery({
    queryKey: deliveryKeys.list(filters),
    queryFn: () =>
      apiClient.get<PaginatedDeliveries>(`/delivery?${qs}`),
    placeholderData: (prev) => prev,
  });
}

// ─── Bitta yetkazish ─────────────────────────────────────────────────────────

export function useDelivery(id: string) {
  return useQuery({
    queryKey: deliveryKeys.detail(id),
    queryFn: () => apiClient.get<Delivery>(`/delivery/${id}`),
    enabled: Boolean(id),
  });
}

// ─── Holat o'zgartirish ───────────────────────────────────────────────────────

export function useUpdateDeliveryStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: DeliveryStatusUpdate }) =>
      apiClient.patch<Delivery>(`/delivery/${id}/status`, data),
    onSuccess: (_result, { id }) => {
      void queryClient.invalidateQueries({ queryKey: deliveryKeys.all });
      void queryClient.invalidateQueries({ queryKey: deliveryKeys.detail(id) });
    },
  });
}

// ─── Kuryer tayinlash (yangi yetkazish yaratish) ──────────────────────────────

export function useAssignCourier() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: DeliveryCreate) =>
      apiClient.post<Delivery>("/delivery", data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: deliveryKeys.all });
    },
  });
}

// ─── Isbot rasm yuklash ───────────────────────────────────────────────────────

export function useUploadProofPhoto() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, file }: { id: string; file: File }) => {
      const formData = new FormData();
      formData.append("file", file);
      return apiClient.upload<Delivery>(`/delivery/${id}/proof-photo`, formData);
    },
    onSuccess: (_result, { id }) => {
      void queryClient.invalidateQueries({ queryKey: deliveryKeys.all });
      void queryClient.invalidateQueries({ queryKey: deliveryKeys.detail(id) });
    },
  });
}

// ─── Marketplace kuryer yetkazishlari ─────────────────────────────────────────

/**
 * Kuryer uchun: o'ziga tayinlangan marketplace buyurtmalar (status=delivering).
 * GET /marketplace/orders/deliveries
 */
export function useMarketplaceCourierDeliveries(
  filters: { limit?: number; offset?: number } = {},
) {
  const limit = filters.limit ?? 20;
  const offset = filters.offset ?? 0;
  const page = Math.floor(offset / limit) + 1;

  return useQuery({
    queryKey: deliveryKeys.courierDeliveries(filters),
    queryFn: () =>
      apiClient.get<PaginatedIncomingOrders>(
        `/marketplace/orders/deliveries?page=${page}&limit=${limit}`,
      ),
    placeholderData: (prev) => prev,
  });
}

// ─── Marketplace isbot rasm yuklash (kuryer) ──────────────────────────────────

export function useMarketplaceUploadProofPhoto() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ orderId, file }: { orderId: string; file: File }) => {
      const formData = new FormData();
      formData.append("file", file);
      return apiClient.upload<IncomingOrder>(
        `/marketplace/orders/${orderId}/proof-photo`,
        formData,
      );
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: deliveryKeys.courierDeliveries() });
      void queryClient.invalidateQueries({ queryKey: ["marketplace"] });
    },
  });
}
