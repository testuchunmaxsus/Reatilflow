/**
 * Agent Cabinet API — TanStack Query hook'lari.
 *
 * Ishlatilgan backend endpointlari:
 *   GET   /auth/me              — joriy agent profili (MeResponse)
 *   PATCH /users/{id}           — profil yangilash (UserUpdate: full_name, locale, version)
 *   GET   /customers/stores     — agent o'z do'konlari
 *                                 (backend agent scope: agent_id = current_user.id)
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type { MeResponse } from "@/api/types";
import { agentProfileFromMe } from "../types";
import type { AgentProfileUpdate, AgentStoreFilters, AgentStoresPage } from "../types";

// ─── Query keys ───────────────────────────────────────────────────────────────

export const agentCabinetKeys = {
  all: ["agent-cabinet"] as const,
  profile: () => [...agentCabinetKeys.all, "profile"] as const,
  stores: (filters?: AgentStoreFilters) =>
    [...agentCabinetKeys.all, "stores", filters ?? {}] as const,
};

// ─── Agent profili ─────────────────────────────────────────────────────────────
// Endpoint: GET /auth/me — access token bo'yicha joriy foydalanuvchi

export function useAgentProfile() {
  return useQuery({
    queryKey: agentCabinetKeys.profile(),
    queryFn: async () => {
      const me = await apiClient.get<MeResponse>("/auth/me");
      return agentProfileFromMe(me);
    },
    staleTime: 1000 * 60 * 5, // 5 daqiqa
  });
}

// ─── Profil yangilash ──────────────────────────────────────────────────────────
// Endpoint: PATCH /auth/me — self-service profil (full_name + locale).
// Har qanday autentifikatsiyalangan rol O'Z profilini yangilay oladi
// (alohida RBAC ruxsati kerak emas — /users/{id} admin-gated edi, agent uchun 403).

export function useUpdateAgentProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: AgentProfileUpdate) =>
      apiClient.patch<MeResponse>("/auth/me", data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: agentCabinetKeys.profile() });
    },
  });
}

// ─── Agent biriktirilgan do'konlar ────────────────────────────────────────────
// Endpoint: GET /customers/stores — backend agent scope orqali filtrlaydi
// (agent roli: faqat o'z agent_id ga biriktirilgan do'konlar qaytadi)

export function useAgentStores(filters: AgentStoreFilters = {}) {
  const params = new URLSearchParams();
  if (filters.search_name) params.set("search_name", filters.search_name);
  params.set("limit", String(filters.limit ?? 20));
  params.set("offset", String(filters.offset ?? 0));
  const qs = params.toString();

  return useQuery({
    queryKey: agentCabinetKeys.stores(filters),
    queryFn: () =>
      apiClient.get<AgentStoresPage>(`/customers/stores?${qs}`),
    placeholderData: (prev) => prev,
    staleTime: 1000 * 60 * 2, // 2 daqiqa
  });
}
