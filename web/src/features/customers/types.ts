/**
 * Mijoz bazasi feature tiplaari — CUSTOMERS.md §6 ga mos.
 */

export type { StoreOut } from "@/api/types";

// ─── Cheklangan javob (kuryer roli) ──────────────────────────────────────────

export interface StoreLimitedOut {
  id: string;
  name: string;
  address: string;
  gps_lat: string | null;
  gps_lng: string | null;
}

// ─── Paginated javob ─────────────────────────────────────────────────────────

export interface PaginatedStores {
  items: import("@/api/types").StoreOut[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Forma tiplaari ───────────────────────────────────────────────────────────

export interface StoreCreate {
  name: string;
  inn?: string | null;
  inps?: string | null;
  owner_name?: string | null;
  phone?: string | null;
  address?: string | null;
  gps_lat?: string | null;
  gps_lng?: string | null;
  segment_id?: string | null;
  agent_id?: string | null;
  branch_id?: string | null;
  credit_limit?: string | null;
  user_id?: string | null;
  client_uuid?: string;
}

export interface StoreUpdate {
  name?: string;
  inn?: string | null;
  inps?: string | null;
  owner_name?: string | null;
  phone?: string | null;
  address?: string | null;
  gps_lat?: string | null;
  gps_lng?: string | null;
  segment_id?: string | null;
  credit_limit?: string | null;
  version: number; // optimistik lock — majburiy
}

export interface AssignAgentRequest {
  agent_id: string;
}

export interface AssignAgentResponse {
  store_id: string;
  agent_id: string;
  assigned_at: string;
}

// ─── Filtr tipi ───────────────────────────────────────────────────────────────

export interface StoreFilters {
  search_name?: string;
  search_inn?: string;
  search_phone?: string;
  limit?: number;
  offset?: number;
}
