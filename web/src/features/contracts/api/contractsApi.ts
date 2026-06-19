/**
 * Contracts API — TanStack Query hook'lari va API chaqiruvlar.
 *
 * Backend endpointlari (contracts/router.py):
 *   GET    /contracts              — paginated ro'yxat
 *   POST   /contracts              — yaratish (admin/accountant)
 *   GET    /contracts/{id}         — bitta shartnoma
 *   PATCH  /contracts/{id}         — yangilash (version optimistik lock)
 *   POST   /contracts/{id}/file    — fayl yuklash (multipart/form-data)
 *   DELETE /contracts/{id}         — soft-delete (admin only)
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type {
  ContractOut,
  PaginatedContracts,
  ContractCreate,
  ContractUpdate,
  ContractFilters,
} from "../types";

// ─── Query keys ───────────────────────────────────────────────────────────────

export const contractKeys = {
  all: ["contracts"] as const,
  list: (filters?: ContractFilters) =>
    [...contractKeys.all, "list", filters ?? {}] as const,
  detail: (id: string) => [...contractKeys.all, "detail", id] as const,
};

// ─── Ro'yxat ──────────────────────────────────────────────────────────────────

export function useContracts(filters: ContractFilters = {}) {
  const params = new URLSearchParams();
  if (filters.store_id) params.set("store_id", filters.store_id);
  if (filters.status) params.set("status", filters.status);
  if (filters.valid_to_before) params.set("valid_to_before", filters.valid_to_before);
  if (filters.valid_to_after) params.set("valid_to_after", filters.valid_to_after);
  params.set("limit", String(filters.limit ?? 20));
  params.set("offset", String(filters.offset ?? 0));

  const qs = params.toString();

  return useQuery({
    queryKey: contractKeys.list(filters),
    queryFn: () => apiClient.get<PaginatedContracts>(`/contracts?${qs}`),
    placeholderData: (prev) => prev,
  });
}

// ─── Bitta shartnoma ──────────────────────────────────────────────────────────

export function useContract(id: string, enabled = true) {
  return useQuery({
    queryKey: contractKeys.detail(id),
    queryFn: () => apiClient.get<ContractOut>(`/contracts/${id}`),
    enabled,
  });
}

// ─── Yaratish ─────────────────────────────────────────────────────────────────

export function useCreateContract() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: ContractCreate) =>
      apiClient.post<ContractOut>("/contracts", data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: contractKeys.all });
    },
  });
}

// ─── Yangilash (PATCH) ────────────────────────────────────────────────────────

export function useUpdateContract() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ContractUpdate }) =>
      apiClient.patch<ContractOut>(`/contracts/${id}`, data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: contractKeys.all });
    },
  });
}

// ─── Fayl yuklash (multipart/form-data) ──────────────────────────────────────

export function useUploadContractFile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, file }: { id: string; file: File }) => {
      const formData = new FormData();
      formData.append("file", file);
      return apiClient.upload<ContractOut>(`/contracts/${id}/file`, formData);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: contractKeys.all });
    },
  });
}

// ─── O'chirish (soft-delete) ──────────────────────────────────────────────────

export function useDeleteContract() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiClient.delete<void>(`/contracts/${id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: contractKeys.all });
    },
  });
}
