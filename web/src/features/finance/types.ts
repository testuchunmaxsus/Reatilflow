/**
 * Finance feature tiplaari — backend schemas.py ga mos.
 *
 * Backend endpointlari (finance/router.py):
 *   POST /finance/ledger                  — LedgerEntryOut (201, finance:create)
 *   POST /finance/ledger/{id}/approve     — LedgerApproveOut (200, finance:approve)
 *   GET  /finance/balance/{store_id}      — AccountBalanceOut (finance:view)
 *   GET  /finance/ledger                  — PaginatedLedger (finance:view)
 *
 * amount — string sifatida keladi (Decimal → JSON string); formatlash frontendda.
 * APPEND-ONLY: yozuvlar hech qachon o'chirilmaydi yoki yangilanmaydi.
 */

// ─── LedgerEntry ──────────────────────────────────────────────────────────────

export interface LedgerEntry {
  id: string;
  store_id: string;
  /** "debit" | "credit" */
  type: string;
  /** Decimal string, masalan "12500.00" */
  amount: string;
  currency: string;
  ref_type: string | null;
  ref_id: string | null;
  entry_date: string;
  created_by: string | null;
  client_uuid: string | null;
  created_at: string;
}

// ─── AccountBalance ───────────────────────────────────────────────────────────

export interface AccountBalance {
  id: string;
  store_id: string;
  /** Decimal string */
  balance: string;
  currency: string;
  last_recalc_at: string;
  version: number;
}

// ─── Paginated ────────────────────────────────────────────────────────────────

export interface PaginatedLedger {
  items: LedgerEntry[];
  total: number;
  limit: number;
  offset: number;
}

// ─── LedgerApproveOut ─────────────────────────────────────────────────────────

export interface LedgerApproveOut {
  id: string;
  entry_id: string;
  approved_by: string;
  approved_at: string;
}

// ─── Yaratish so'rovi ─────────────────────────────────────────────────────────

export interface LedgerEntryCreate {
  store_id: string;
  type: "debit" | "credit";
  /** Musbat raqam string, masalan "5000.00" */
  amount: string;
  currency?: string;
  ref_type?: string | null;
  ref_id?: string | null;
  client_uuid?: string | null;
}

// ─── Filtrlar ─────────────────────────────────────────────────────────────────

export interface LedgerFilters {
  store_id?: string;
  entry_type?: "debit" | "credit" | "";
  limit?: number;
  offset?: number;
}
