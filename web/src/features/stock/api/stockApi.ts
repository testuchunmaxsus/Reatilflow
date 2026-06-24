/**
 * Stock API — TanStack Query hook'lari va API chaqiruvlar.
 *
 * Endpointlar (backend/app/modules/stock/router.py):
 *   GET  /stock/movements   — paginated harakatlar ro'yxati (stock:view)
 *   GET  /stock/balance     — mahsulot qoldig'i (stock:view)
 *   POST /stock/movements   — harakat qayd etish (stock:create, admin only)
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type {
  StockMovementOut,
  StockBalanceOut,
  PaginatedMovements,
  StockMovementCreate,
  StockMovementFilters,
} from "../types";

// ─── Query keys ──────────────────────────────────────────────────────────────

export const stockKeys = {
  all: ["stock"] as const,
  movements: (filters?: StockMovementFilters) =>
    [...stockKeys.all, "movements", filters ?? {}] as const,
  balance: (productId: string, warehouseId: string) =>
    [...stockKeys.all, "balance", productId, warehouseId] as const,
};

// ─── Harakatlar ro'yxati (paginated) ─────────────────────────────────────────

export function useStockMovements(filters: StockMovementFilters = {}) {
  const params = new URLSearchParams();
  if (filters.product_id) params.set("product_id", filters.product_id);
  if (filters.warehouse_id) params.set("warehouse_id", filters.warehouse_id);
  if (filters.movement_type) params.set("movement_type", filters.movement_type);
  params.set("limit", String(filters.limit ?? 20));
  params.set("offset", String(filters.offset ?? 0));

  const qs = params.toString();

  return useQuery({
    queryKey: stockKeys.movements(filters),
    queryFn: () =>
      apiClient.get<PaginatedMovements>(`/stock/movements?${qs}`),
    placeholderData: (prev) => prev,
  });
}

// ─── Qoldiq olish ─────────────────────────────────────────────────────────────

export function useStockBalance(
  productId: string,
  warehouseId: string,
  enabled = true,
) {
  return useQuery({
    queryKey: stockKeys.balance(productId, warehouseId),
    queryFn: () =>
      apiClient.get<StockBalanceOut>(
        `/stock/balance?product_id=${productId}&warehouse_id=${warehouseId}`,
      ),
    enabled: enabled && Boolean(productId) && Boolean(warehouseId),
  });
}

// ─── Harakat yaratish (admin: stock:create) ───────────────────────────────────

export function useCreateStockMovement() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: StockMovementCreate) =>
      apiClient.post<StockMovementOut>("/stock/movements", data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: stockKeys.all });
    },
  });
}
