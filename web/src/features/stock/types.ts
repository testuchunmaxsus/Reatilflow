/**
 * Stock feature tiplaari — backend schemas.py ga mos.
 *
 * Asosiy tiplar backend StockMovementOut, StockBalanceOut, PaginatedMovements
 * dan olingan. Harakat turlari: in | out | transfer | adjust (APPEND-ONLY ledger).
 */

// ─── Harakat turlari ─────────────────────────────────────────────────────────

export type MovementType = "in" | "out" | "transfer" | "adjust";

// ─── Ombor harakati (OUT) ────────────────────────────────────────────────────

export interface StockMovementOut {
  id: string;
  product_id: string;
  warehouse_id: string;
  type: MovementType;
  /** Decimal string — server tomonida Decimal formatida keladi */
  qty: string;
  ref_type: string | null;
  ref_id: string | null;
  moved_by: string | null;
  moved_at: string;
  client_uuid: string | null;
  created_at: string;
}

// ─── Ombor qoldig'i (OUT) ────────────────────────────────────────────────────

export interface StockBalanceOut {
  id: string;
  product_id: string;
  warehouse_id: string;
  /** Decimal string */
  qty_on_hand: string;
  /** Decimal string */
  qty_reserved: string;
  version: number;
  updated_at: string;
}

// ─── Paginated harakatlar ────────────────────────────────────────────────────

export interface PaginatedMovements {
  items: StockMovementOut[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Forma tiplaari (POST) ───────────────────────────────────────────────────

export interface StockMovementCreate {
  product_id: string;
  warehouse_id: string;
  type: MovementType;
  /** Musbat Decimal string ("10", "0.5" va h.k.) */
  qty: string;
  ref_type?: string | null;
  ref_id?: string | null;
  client_uuid?: string | null;
}

// ─── Filtr tiplaari ──────────────────────────────────────────────────────────

export interface StockMovementFilters {
  product_id?: string | null;
  warehouse_id?: string | null;
  movement_type?: MovementType | null;
  limit?: number;
  offset?: number;
}
