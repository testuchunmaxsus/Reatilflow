/**
 * Tickets API — TanStack Query hook'lari va API chaqiruvlar.
 *
 * Backend endpointlari (tickets/router.py):
 *   GET    /tickets               — paginated ro'yxat (RBAC scope)
 *   POST   /tickets               — yaratish
 *   GET    /tickets/{id}          — murojaat (messages bilan)
 *   POST   /tickets/{id}/messages — xabar qo'shish
 *   PATCH  /tickets/{id}/status   — holat o'zgartirish (admin/accountant)
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type {
  TicketOut,
  PaginatedTickets,
  TicketCreate,
  TicketStatusUpdate,
  TicketMessageCreate,
  TicketMessageOut,
  TicketFilters,
} from "../types";

// ─── Query keys ───────────────────────────────────────────────────────────────

export const ticketKeys = {
  all: ["tickets"] as const,
  list: (filters?: TicketFilters) =>
    [...ticketKeys.all, "list", filters ?? {}] as const,
  detail: (id: string) => [...ticketKeys.all, "detail", id] as const,
};

// ─── Ro'yxat ──────────────────────────────────────────────────────────────────

export function useTickets(filters: TicketFilters = {}) {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.ticket_type) params.set("ticket_type", filters.ticket_type);
  if (filters.store_id) params.set("store_id", filters.store_id);
  params.set("limit", String(filters.limit ?? 20));
  params.set("offset", String(filters.offset ?? 0));

  const qs = params.toString();

  return useQuery({
    queryKey: ticketKeys.list(filters),
    queryFn: () => apiClient.get<PaginatedTickets>(`/tickets?${qs}`),
    placeholderData: (prev) => prev,
  });
}

// ─── Bitta murojaat (messages bilan) ─────────────────────────────────────────

export function useTicket(id: string, enabled = true) {
  return useQuery({
    queryKey: ticketKeys.detail(id),
    queryFn: () => apiClient.get<TicketOut>(`/tickets/${id}`),
    enabled,
  });
}

// ─── Yaratish ─────────────────────────────────────────────────────────────────

export function useCreateTicket() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: TicketCreate) =>
      apiClient.post<TicketOut>("/tickets", data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ticketKeys.all });
    },
  });
}

// ─── Xabar qo'shish ───────────────────────────────────────────────────────────

export function useAddTicketMessage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      ticketId,
      data,
    }: {
      ticketId: string;
      data: TicketMessageCreate;
    }) =>
      apiClient.post<TicketMessageOut>(
        `/tickets/${ticketId}/messages`,
        data,
      ),
    onSuccess: (_result, variables) => {
      void queryClient.invalidateQueries({
        queryKey: ticketKeys.detail(variables.ticketId),
      });
      void queryClient.invalidateQueries({ queryKey: ticketKeys.all });
    },
  });
}

// ─── Holat o'zgartirish ───────────────────────────────────────────────────────

export function useUpdateTicketStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      ticketId,
      data,
    }: {
      ticketId: string;
      data: TicketStatusUpdate;
    }) =>
      apiClient.patch<TicketOut>(`/tickets/${ticketId}/status`, data),
    onSuccess: (_result, variables) => {
      void queryClient.invalidateQueries({
        queryKey: ticketKeys.detail(variables.ticketId),
      });
      void queryClient.invalidateQueries({ queryKey: ticketKeys.all });
    },
  });
}
