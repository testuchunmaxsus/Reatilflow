/**
 * Finance API — TanStack Query hook'lari va API chaqiruvlar.
 *
 * Backend endpointlari (finance/router.py):
 *   GET  /finance/ledger                — paginated ro'yxat (finance:view)
 *   GET  /finance/balance/{store_id}    — balans (finance:view)
 *   POST /finance/ledger                — yozuv qayd etish (finance:create)
 *   POST /finance/ledger/{id}/approve   — tasdiqlash (finance:approve)
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type {
  LedgerEntry,
  PaginatedLedger,
  AccountBalance,
  LedgerEntryCreate,
  LedgerApproveOut,
  LedgerFilters,
} from "../types";

// ─── Query keys ───────────────────────────────────────────────────────────────

export const financeKeys = {
  all: ["finance"] as const,
  ledger: (filters?: LedgerFilters) =>
    [...financeKeys.all, "ledger", filters ?? {}] as const,
  balance: (storeId: string) =>
    [...financeKeys.all, "balance", storeId] as const,
};

// ─── Ledger ro'yxati ──────────────────────────────────────────────────────────

export function useLedger(filters: LedgerFilters = {}) {
  const params = new URLSearchParams();
  if (filters.store_id) params.set("store_id", filters.store_id);
  if (filters.entry_type) params.set("entry_type", filters.entry_type);
  params.set("limit", String(filters.limit ?? 20));
  params.set("offset", String(filters.offset ?? 0));

  const qs = params.toString();

  return useQuery({
    queryKey: financeKeys.ledger(filters),
    queryFn: () => apiClient.get<PaginatedLedger>(`/finance/ledger?${qs}`),
    placeholderData: (prev) => prev,
  });
}

// ─── Balans ───────────────────────────────────────────────────────────────────

export function useBalance(storeId: string, enabled = true) {
  return useQuery({
    queryKey: financeKeys.balance(storeId),
    queryFn: () =>
      apiClient.get<AccountBalance>(`/finance/balance/${storeId}`),
    enabled: enabled && !!storeId,
  });
}

// ─── Yozuv qayd etish ─────────────────────────────────────────────────────────

export function useCreateLedgerEntry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: LedgerEntryCreate) =>
      apiClient.post<LedgerEntry>("/finance/ledger", data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: financeKeys.all });
    },
  });
}

// ─── Tasdiqlash ───────────────────────────────────────────────────────────────

export function useApproveLedgerEntry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (entryId: string) =>
      apiClient.post<LedgerApproveOut>(
        `/finance/ledger/${entryId}/approve`,
        {},
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: financeKeys.all });
    },
  });
}
