/**
 * Agent Cabinet feature tiplari.
 *
 * Backend endpointlari:
 *   GET  /auth/me                          — agent profili (MeResponse)
 *   PATCH /users/{id}                      — profil yangilash (version lock)
 *   GET  /customers/stores                 — agent biriktirilgan do'konlar
 *                                            (backend scope: agent → o'z do'konlari)
 */

import type { MeResponse } from "@/api/types";
import type { StoreOut } from "@/api/types";

// ─── Profil ───────────────────────────────────────────────────────────────────

/** Agent profili — /auth/me javobiga mos */
export interface AgentProfile {
  id: string;
  full_name: string;
  phone: string;
  role: string;
  branch_id: string | null;
  locale: "uz" | "ru";
  is_active: boolean;
  permissions: string[];
}

/** AgentProfile ni MeResponse dan tuzish */
export function agentProfileFromMe(me: MeResponse): AgentProfile {
  return {
    id: me.id,
    full_name: me.full_name,
    phone: me.phone,
    role: me.role,
    branch_id: me.branch_id,
    locale: me.locale,
    is_active: me.is_active,
    permissions: me.permissions ?? [],
  };
}

// ─── Profil yangilash ─────────────────────────────────────────────────────────

/** PATCH /auth/me tanasi — self-service profil (full_name + locale) */
export interface AgentProfileUpdate {
  full_name?: string;
  locale?: "uz" | "ru";
}

// ─── Do'konlar ────────────────────────────────────────────────────────────────

/** Agent biriktirilgan do'konlar sahifasi */
export interface AgentStoresPage {
  items: StoreOut[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Filtrlar ─────────────────────────────────────────────────────────────────

export interface AgentStoreFilters {
  search_name?: string;
  limit?: number;
  offset?: number;
}
