/**
 * Contracts feature tiplaari — backend schemas.py ga mos.
 *
 * Backend endpointlari (contracts/router.py):
 *   GET    /contracts              — PaginatedContracts
 *   POST   /contracts              — ContractOut (201)
 *   GET    /contracts/{id}         — ContractOut
 *   PATCH  /contracts/{id}         — ContractOut (optimistik lock: version majburiy)
 *   POST   /contracts/{id}/file    — ContractOut (fayl yuklash)
 *   DELETE /contracts/{id}         — 204 (soft-delete)
 *
 * status DERIVED (backend hisoblaydi):
 *   active   — valid_to - bugun > 30 kun
 *   expiring — valid_to - bugun <= 30 kun
 *   expired  — valid_to < bugun
 */

// ─── Javob ────────────────────────────────────────────────────────────────────

export interface ContractOut {
  id: string;
  store_id: string;
  number: string;
  file_url: string | null;
  signed_at: string | null;
  valid_from: string;
  valid_to: string;
  contract_type: string | null;
  branch_id: string | null;
  client_uuid: string | null;
  /** DERIVED from valid_to: "active" | "expiring" | "expired" */
  status: "active" | "expiring" | "expired";
  version: number;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

// ─── Paginated ────────────────────────────────────────────────────────────────

export interface PaginatedContracts {
  items: ContractOut[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Yaratish ─────────────────────────────────────────────────────────────────

export interface ContractCreate {
  store_id: string;
  number: string;
  valid_from: string;
  valid_to: string;
  signed_at?: string | null;
  contract_type?: string | null;
  branch_id?: string | null;
  client_uuid?: string | null;
}

// ─── Yangilash (PATCH) ────────────────────────────────────────────────────────

export interface ContractUpdate {
  number?: string;
  valid_from?: string;
  valid_to?: string;
  signed_at?: string | null;
  contract_type?: string | null;
  branch_id?: string | null;
  version: number;
}

// ─── Filtrlar ─────────────────────────────────────────────────────────────────

export interface ContractFilters {
  store_id?: string;
  status?: "active" | "expiring" | "expired" | "";
  valid_to_before?: string;
  valid_to_after?: string;
  limit?: number;
  offset?: number;
}
