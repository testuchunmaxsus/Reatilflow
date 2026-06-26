/**
 * Buyurtma feature tiplaari — ORDERS.md ga mos.
 *
 * Server-avtoritar qoidasi (T11):
 *   OrderLineIn faqat product_id + qty. Narx, segment, discount KLIENT TOMONIDA YUBORILMAYDI.
 */

// ─── Holat mashinasi ─────────────────────────────────────────────────────────

export type OrderStatus =
  | "draft"
  | "confirmed"
  | "packed"
  | "delivering"
  | "delivered"
  | "canceled";

export type OrderMode = "bozor" | "oddiy";

/**
 * Server VALID_TRANSITIONS dan — qonuniy o'tishlar (ORDERS.md §4).
 * POST /orders confirmed dan boshlanadi, shuning uchun draft UI dan yaratilmaydi.
 */
export const VALID_TRANSITIONS: Record<OrderStatus, OrderStatus[]> = {
  draft: ["confirmed", "canceled"],
  confirmed: ["packed", "canceled"],
  packed: ["delivering", "canceled"],
  delivering: ["delivered", "canceled"],
  delivered: [],
  canceled: [],
};

// ─── Order line ───────────────────────────────────────────────────────────────

/** Server javobidagi buyurtma qatori */
export interface OrderLineOut {
  id: string;
  order_id: string;
  product_id: string;
  qty: string;
  unit_price: string;
  segment_id: string | null;
  discount: string;
  line_total: string;
}

/** POST /orders uchun klient yuboradigan qator — faqat product_id + qty (T11) */
export interface OrderLineIn {
  product_id: string;
  qty: string;
}

// ─── Order ────────────────────────────────────────────────────────────────────

/** GET /orders va GET /orders/{id} javobi */
export interface OrderOut {
  id: string;
  store_id: string;
  agent_id: string | null;
  mode: OrderMode;
  status: OrderStatus;
  total_amount: string;
  currency: string;
  ordered_at: string;
  client_uuid: string | null;
  branch_id: string | null;
  warehouse_id: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  lines: OrderLineOut[];
}

/** POST /orders uchun so'rov */
export interface OrderCreate {
  store_id: string;
  mode: OrderMode;
  currency?: string;
  client_uuid?: string;
  /** Ixtiyoriy — bo'sh bo'lsa server default omborni ishlatadi */
  warehouse_id?: string;
  lines: OrderLineIn[];
}

/** PATCH /orders/{id}/status uchun so'rov */
export interface OrderStatusUpdate {
  status: OrderStatus;
  version: number;
}

// ─── Paginated javob ──────────────────────────────────────────────────────────

export interface PaginatedOrders {
  items: OrderOut[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Filtr tipi ───────────────────────────────────────────────────────────────

export interface OrderFilters {
  status?: OrderStatus | null;
  store_id?: string | null;
  agent_id?: string | null;
  from?: string | null;
  to?: string | null;
  limit?: number;
  offset?: number;
}

// ─── Buyurtma shablonlari ─────────────────────────────────────────────────────

/** Shablon qatori — faqat product_id + qty (T11 bilan bir xil) */
export interface TemplateLineIn {
  product_id: string;
  qty: string;
}

/** POST /orders/templates uchun so'rov */
export interface OrderTemplateCreate {
  name: string;
  store_id: string;
  lines: TemplateLineIn[];
}

/** GET /orders/templates javobidagi bitta shablon */
export interface OrderTemplateOut {
  id: string;
  name: string;
  store_id: string;
  lines: TemplateLineIn[];
  created_at: string;
}

/** POST /orders/templates/{id}/apply javobi — yaratilgan buyurtma */
export type OrderTemplateApplyOut = OrderOut;
