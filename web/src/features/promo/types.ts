/**
 * Promo (Aksiya) feature tiplaari — backend schemas.py ga mos.
 *
 * Backend endpointlari (promo/router.py):
 *   GET    /promos          — PaginatedPromos
 *   GET    /promos/active   — PromoOut[] (bugun aktiv)
 *   POST   /promos          — PromoOut (201, faqat administrator)
 *   GET    /promos/{id}     — PromoOut
 *   PATCH  /promos/{id}     — PromoOut (optimistik lock)
 *   POST   /promos/{id}/banner — PromoOut (banner yuklash)
 *   DELETE /promos/{id}     — 204 (soft-delete)
 *
 * rule_json qoidalari (server-avtoritar — discount backend da hisoblanadi):
 *   {"discount_percent": 10}
 *   {"discount_amount": 5000}
 *   {"discount_percent": 15, "min_qty": 3}
 *   {"discount_amount": 2000, "min_qty": 2}
 */

// ─── rule_json ────────────────────────────────────────────────────────────────

export interface RuleJson {
  discount_percent?: number;
  discount_amount?: number;
  min_qty?: number;
  [key: string]: unknown;
}

// ─── Javob ────────────────────────────────────────────────────────────────────

export interface PromoOut {
  id: string;
  name_uz: string;
  name_ru: string;
  /** Lokalizatsiyalangan nom (backend to'ldiradi) */
  name: string;
  promo_type: string;
  rule_json: RuleJson;
  banner_url: string | null;
  valid_from: string;
  valid_to: string;
  target_segment_id: string | null;
  target_product_id: string | null;
  is_active: boolean;
  branch_id: string | null;
  client_uuid: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  /** Marketplace: qaynoq aksiya belgisi (ixtiyoriy — marketplace moduli yoqilganda keladi) */
  is_marketplace_featured?: boolean;
}

// ─── Paginated ────────────────────────────────────────────────────────────────

export interface PaginatedPromos {
  items: PromoOut[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Yaratish ─────────────────────────────────────────────────────────────────

export interface PromoCreate {
  name_uz: string;
  name_ru: string;
  promo_type?: string;
  rule_json: RuleJson;
  banner_url?: string | null;
  valid_from: string;
  valid_to: string;
  target_segment_id?: string | null;
  target_product_id?: string | null;
  is_active?: boolean;
  branch_id?: string | null;
  client_uuid?: string | null;
}

// ─── Yangilash (PATCH) ────────────────────────────────────────────────────────

export interface PromoUpdate {
  version: number;
  name_uz?: string;
  name_ru?: string;
  promo_type?: string;
  rule_json?: RuleJson;
  valid_from?: string;
  valid_to?: string;
  target_segment_id?: string | null;
  target_product_id?: string | null;
  is_active?: boolean;
  branch_id?: string | null;
}

// ─── Filtrlar ─────────────────────────────────────────────────────────────────

export interface PromoFilters {
  is_active?: boolean;
  target_segment_id?: string;
  target_product_id?: string;
  promo_type?: string;
  limit?: number;
  offset?: number;
}
