/**
 * Marketplace API — TanStack Query hook'lari va API chaqiruvlar.
 *
 * Endpointlar:
 *   GET    /marketplace/products               — cross-tenant katalog browse
 *   GET    /marketplace/suppliers              — supplierlar ro'yxati
 *   POST   /marketplace/orders                 — buyurtma yaratish
 *   GET    /marketplace/orders/incoming        — kiruvchi buyurtmalar
 *   PATCH  /marketplace/orders/{id}/confirm    — tasdiqlash
 *   PATCH  /marketplace/orders/{id}/reject     — rad etish
 *   PATCH  /marketplace/orders/{id}/ship       — kuryer tayinlash + jo'natish
 *   GET    /marketplace/orders/outgoing        — chiquvchi buyurtmalar
 *   PATCH  /catalog/products/{id}/marketplace  — mahsulot publish toggle
 *   GET    /marketplace/banners                — bannerlar ro'yxati
 *   POST   /marketplace/banners               — banner yaratish
 *   PATCH  /marketplace/banners/{id}          — banner tahrirlash
 *   DELETE /marketplace/banners/{id}          — banner o'chirish
 *   POST   /marketplace/banners/{id}/image    — banner rasmi yuklash
 *   PATCH  /promos/{id}/marketplace-featured  — aksiya featured toggle
 *   GET    /users?role=courier                — kuryerlar ro'yxati
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type {
  PaginatedIncomingOrders,
  PaginatedOutgoingOrders,
  IncomingOrder,
  OutgoingOrder,
  PaginatedBanners,
  BannerOut,
  BannerCreate,
  BannerUpdate,
  MarketplacePublishPayload,
  MarketplaceFeaturedPayload,
  AcceptOrderPayload,
  RejectOrderPayload,
  OrderFilters,
  PaginatedMarketplaceProducts,
  MarketplaceSupplierOut,
  MarketplaceOrderCreate,
  MarketplaceBrowseFilters,
} from "../types";
import type { AppUserOut } from "@/api/types";

// ─── Query keys ───────────────────────────────────────────────────────────────

export const marketplaceKeys = {
  all: ["marketplace"] as const,
  incomingOrders: (filters?: OrderFilters) =>
    [...marketplaceKeys.all, "incoming", filters ?? {}] as const,
  outgoingOrders: (filters?: OrderFilters) =>
    [...marketplaceKeys.all, "outgoing", filters ?? {}] as const,
  banners: (filters?: { limit?: number; offset?: number }) =>
    [...marketplaceKeys.all, "banners", filters ?? {}] as const,
  couriers: () => [...marketplaceKeys.all, "couriers"] as const,
  browse: (filters?: MarketplaceBrowseFilters) =>
    [...marketplaceKeys.all, "browse", filters ?? {}] as const,
  suppliers: () => [...marketplaceKeys.all, "suppliers"] as const,
};

// ─── Kiruvchi buyurtmalar ─────────────────────────────────────────────────────

export function useIncomingOrders(filters: OrderFilters = {}) {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  params.set("limit", String(filters.limit ?? 20));
  params.set("offset", String(filters.offset ?? 0));
  const qs = params.toString();

  return useQuery({
    queryKey: marketplaceKeys.incomingOrders(filters),
    queryFn: () =>
      apiClient.get<PaginatedIncomingOrders>(
        `/marketplace/orders/incoming?${qs}`,
      ),
    placeholderData: (prev) => prev,
  });
}

// ─── Buyurtmani tasdiqlash ────────────────────────────────────────────────────

export function useConfirmOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiClient.patch<IncomingOrder>(`/marketplace/orders/${id}/confirm`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: marketplaceKeys.all });
    },
  });
}

// ─── Buyurtmani rad etish ─────────────────────────────────────────────────────

export function useRejectOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload?: RejectOrderPayload }) =>
      apiClient.patch<IncomingOrder>(
        `/marketplace/orders/${id}/reject`,
        payload ?? {},
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: marketplaceKeys.all });
    },
  });
}

// ─── Buyurtmani qabul qilish (xaridor tomonidan) ──────────────────────────────

export function useAcceptOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: AcceptOrderPayload }) =>
      apiClient.patch<OutgoingOrder>(
        `/marketplace/orders/${id}/accept`,
        payload,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: marketplaceKeys.all });
    },
  });
}

// ─── Kuryer tayinlash va jo'natish ────────────────────────────────────────────

export function useShipOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, courier_id }: { id: string; courier_id: string }) =>
      apiClient.patch<IncomingOrder>(`/marketplace/orders/${id}/ship`, {
        courier_id,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: marketplaceKeys.all });
    },
  });
}

// ─── Chiquvchi buyurtmalar ────────────────────────────────────────────────────

export function useOutgoingOrders(filters: OrderFilters = {}) {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  params.set("limit", String(filters.limit ?? 20));
  params.set("offset", String(filters.offset ?? 0));
  const qs = params.toString();

  return useQuery({
    queryKey: marketplaceKeys.outgoingOrders(filters),
    queryFn: () =>
      apiClient.get<PaginatedOutgoingOrders>(
        `/marketplace/orders/outgoing?${qs}`,
      ),
    placeholderData: (prev) => prev,
  });
}

// ─── Mahsulot marketplace publish toggle ─────────────────────────────────────

export function useToggleMarketplacePublish() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string;
      payload: MarketplacePublishPayload;
    }) =>
      apiClient.patch<unknown>(
        `/catalog/products/${id}/marketplace`,
        payload,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["catalog"] });
    },
  });
}

// ─── Bannerlar ro'yxati ───────────────────────────────────────────────────────

export function useBanners(filters: { limit?: number; offset?: number } = {}) {
  const limit = filters.limit ?? 20;
  const offset = filters.offset ?? 0;
  // Backend page-based: page = offset/limit + 1
  const page = Math.floor(offset / limit) + 1;

  return useQuery({
    queryKey: marketplaceKeys.banners(filters),
    queryFn: () =>
      apiClient.get<PaginatedBanners>(`/marketplace/banners/mine?page=${page}&limit=${limit}`),
    placeholderData: (prev) => prev,
  });
}

// ─── Banner yaratish ──────────────────────────────────────────────────────────

export function useCreateBanner() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: BannerCreate) =>
      apiClient.post<BannerOut>("/marketplace/banners", data),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: marketplaceKeys.banners(),
      });
    },
  });
}

// ─── Banner tahrirlash ────────────────────────────────────────────────────────

export function useUpdateBanner() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: BannerUpdate }) =>
      apiClient.patch<BannerOut>(`/marketplace/banners/${id}`, data),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: marketplaceKeys.banners(),
      });
    },
  });
}

// ─── Banner o'chirish ─────────────────────────────────────────────────────────

export function useDeleteBanner() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiClient.delete<void>(`/marketplace/banners/${id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: marketplaceKeys.banners(),
      });
    },
  });
}

// ─── Banner rasm yuklash ──────────────────────────────────────────────────────

export function useUploadBannerImage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, file }: { id: string; file: File }) => {
      const formData = new FormData();
      formData.append("file", file);
      return apiClient.upload<BannerOut>(
        `/marketplace/banners/${id}/image`,
        formData,
      );
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: marketplaceKeys.banners(),
      });
    },
  });
}

// ─── Aksiya featured toggle ───────────────────────────────────────────────────

export function useToggleMarketplaceFeatured() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string;
      payload: MarketplaceFeaturedPayload;
    }) =>
      apiClient.patch<unknown>(
        `/promos/${id}/marketplace-featured`,
        payload,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["promos"] });
    },
  });
}

// ─── Kuryerlar ro'yxati ───────────────────────────────────────────────────────

export function useCouriers() {
  return useQuery({
    queryKey: marketplaceKeys.couriers(),
    queryFn: () =>
      apiClient.get<{ items: AppUserOut[]; total: number }>(
        "/users?role=courier&limit=100&offset=0",
      ),
    staleTime: 1000 * 60 * 5,
  });
}

// ─── Marketplace katalog browse ───────────────────────────────────────────────

/**
 * GET /marketplace/products — cross-tenant published mahsulotlar.
 * Backend page-based pagination: page=1-bazali.
 */
export function useMarketplaceProducts(filters: MarketplaceBrowseFilters = {}) {
  const page = filters.page ?? 1;
  const limit = filters.limit ?? 20;

  const params = new URLSearchParams();
  if (filters.search) params.set("search", filters.search);
  if (filters.supplier_enterprise) params.set("supplier_enterprise", filters.supplier_enterprise);
  params.set("page", String(page));
  params.set("limit", String(limit));

  const qs = params.toString();

  return useQuery({
    queryKey: marketplaceKeys.browse(filters),
    queryFn: () =>
      apiClient.get<PaginatedMarketplaceProducts>(`/marketplace/products?${qs}`),
    placeholderData: (prev) => prev,
  });
}

// ─── Supplierlar ro'yxati ─────────────────────────────────────────────────────

/**
 * GET /marketplace/suppliers — marketplace'da mahsuloti bor korxonalar.
 * Filter dropdown uchun ishlatiladi.
 */
export function useMarketplaceSuppliers() {
  return useQuery({
    queryKey: marketplaceKeys.suppliers(),
    queryFn: () =>
      apiClient.get<MarketplaceSupplierOut[]>("/marketplace/suppliers"),
    staleTime: 1000 * 60 * 5,
  });
}

// ─── Marketplace buyurtma yaratish ────────────────────────────────────────────

/**
 * POST /marketplace/orders — yangi marketplace buyurtma.
 * 409 marketplace.contract_required → shartnoma-gate xabari ko'rsatiladi.
 */
export function useCreateMarketplaceOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: MarketplaceOrderCreate) =>
      apiClient.post<OutgoingOrder>("/marketplace/orders", {
        lines: payload.lines,
        store_id: payload.buyer_store_id ?? undefined,
        client_uuid: payload.client_uuid ?? undefined,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: marketplaceKeys.all });
    },
  });
}
