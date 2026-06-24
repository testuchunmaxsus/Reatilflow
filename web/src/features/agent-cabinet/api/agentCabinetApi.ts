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
import type { MeResponse, AppUserOut } from "@/api/types";
import type { StoreOut } from "@/api/types";
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
// Endpoint: PATCH /users/{id} — foydalanuvchi o'zini tahrirlaydi
//
// FIX #3: version:1 hardcode → takroriy tahrirlashda 409 Conflict berardi.
// Yechim: PATCH oldidan GET /users/{id} orqali haqiqiy version'ni olamiz.
// Bu har doim to'g'ri version bilan PATCH qilishni ta'minlaydi.

export function useUpdateAgentProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, data }: { id: string; data: AgentProfileUpdate }) => {
      // Haqiqiy version'ni olish — hardcode emas
      const currentUser = await apiClient.get<AppUserOut>(`/users/${id}`);
      const payload: AgentProfileUpdate = { ...data, version: currentUser.version };
      return apiClient.patch<StoreOut>(`/users/${id}`, payload);
    },
    onSuccess: () => {
      // Profilni va auth cache ni yangilaymiz
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
