/**
 * POS feature tiplaari — backend schemas.py ga mos.
 *
 * PosSaleLineIn  — sotuv qatori (POST, faqat product_id + qty)
 * PosSaleCreate  — yangi sotuv so'rovi (checkout)
 * PosSaleLineOut — qator javob
 * PosSaleOut     — sotuv javob (kvitansiya)
 * PaginatedSales — paginated ro'yxat
 * PosSummary     — kunlik statistika (DailySummaryOut)
 * PosInventoryItem — do'kon inventar partiyasi (StoreInventoryOut)
 *
 * XAVFSIZLIK:
 *   unit_price YO'Q — narx server tomonida belgilanadi.
 *   discount YO'Q   — chegirma klient tomonidan berilmaydi.
 */

// ─── Sotuv qatori (kiritiladigan) ─────────────────────────────────────────────

export interface PosSaleLineIn {
  product_id: string;
  qty: number;
}

// ─── Sotuv yaratish so'rovi ────────────────────────────────────────────────────

export interface PosSaleCreate {
  store_id: string;
  /** "cash" | "card" */
  payment_method: string;
  lines: PosSaleLineIn[];
  customer_phone?: string | null;
  /** Idempotentlik UUID (ixtiyoriy) */
  client_uuid?: string | null;
}

// ─── Sotuv qatori (javob) ────────────────────────────────────────────────────

export interface PosSaleLine {
  id: string;
  product_id: string;
  qty: string;
  unit_price: string;
  line_total: string;
}

// ─── Sotuv (javob, kvitansiya) ────────────────────────────────────────────────

export interface PosSale {
  id: string;
  store_id: string;
  cashier_id: string | null;
  enterprise_id: string | null;
  total_amount: string;
  discount_amount: string;
  payment_method: string;
  customer_phone: string | null;
  status: string;
  client_uuid: string | null;
  created_at: string;
  lines: PosSaleLine[];
}

// ─── Paginated sotuvlar ───────────────────────────────────────────────────────

export interface PaginatedPosSales {
  items: PosSale[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Kunlik summary ───────────────────────────────────────────────────────────

export interface PaymentMethodSummary {
  payment_method: string;
  count: number;
  total_amount: string;
}

export interface PosSummary {
  date: string;
  total_sales: number;
  total_amount: string;
  by_payment: PaymentMethodSummary[];
}

// ─── Inventar item (StoreInventoryOut dan) ────────────────────────────────────

export interface PosInventoryItem {
  id: string;
  enterprise_id: string;
  store_id: string;
  product_id: string;
  qty: string;
  cost_price: string;
  markup_percent: string;
  sale_price: string;
  expiry_date: string | null;
  status: "active" | "expired";
  source_order_id: string | null;
  created_at: string;
  /** MP4: server tomonida hisoblanadi */
  is_expired: boolean;
  is_near_expiry: boolean;
  days_to_expiry: number | null;
}

export interface PaginatedPosInventory {
  items: PosInventoryItem[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Savat holati (faqat klient) ──────────────────────────────────────────────

export interface CartItem {
  /** Katalog mahsulot ID */
  product_id: string;
  /** Mahsulot nomi (ko'rsatish uchun) */
  product_name: string;
  qty: number;
  /** Inventar: muddati o'tgan yoki yaqinmi */
  is_expired: boolean;
  is_near_expiry: boolean;
}
