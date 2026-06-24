/**
 * Delivery feature tiplaari — backend schemas.py ga mos.
 *
 * Endpointlar:
 *   POST   /delivery                    — kuryer tayinlash (delivery:create)
 *   PATCH  /delivery/{id}/status        — holat o'zgartirish (delivery:edit)
 *   POST   /delivery/{id}/proof-photo   — isbot rasm yuklash (delivery:edit)
 *   GET    /delivery                    — ro'yxat (delivery:view, RBAC scope)
 *   GET    /delivery/{id}               — bitta yetkazish (delivery:view)
 *
 * Marketplace kuryer:
 *   GET    /marketplace/orders/deliveries  — kuryer o'z marketplace yetkazishlari
 *   POST   /marketplace/orders/{id}/proof-photo — marketplace isbot rasm
 *
 * RBAC scope:
 *   courier  → faqat o'ziga tayinlangan
 *   agent    → o'z buyurtmalari
 *   store    → o'z buyurtmalari
 *   admin    → barchasi
 */

// ─── Holat mashinasi ─────────────────────────────────────────────────────────

export type DeliveryStatus =
  | "assigned"
  | "started"
  | "delivering"
  | "delivered"
  | "failed";

/** Server VALID_TRANSITIONS */
export const DELIVERY_VALID_TRANSITIONS: Record<DeliveryStatus, DeliveryStatus[]> = {
  assigned: ["started"],
  started: ["delivering"],
  delivering: ["delivered", "failed"],
  delivered: [],
  failed: [],
};

// ─── Yetkazish ────────────────────────────────────────────────────────────────

/** GET /delivery va GET /delivery/{id} javobi */
export interface Delivery {
  id: string;
  order_id: string;
  courier_id: string;
  status: DeliveryStatus;
  assigned_at: string;
  started_at: string | null;
  start_gps_lat: string | null;
  start_gps_lng: string | null;
  delivered_at: string | null;
  delivery_gps_lat: string | null;
  delivery_gps_lng: string | null;
  proof_photo_url: string | null;
  failure_reason: string | null;
  branch_id: string | null;
  client_uuid: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  /** GPS trek havolasi — GET /gps/track?delivery_id=... */
  gps_track_url: string | null;
}

// ─── Yaratish / Tahrirlash ────────────────────────────────────────────────────

/** POST /delivery uchun so'rov */
export interface DeliveryCreate {
  order_id: string;
  courier_id: string;
  client_uuid?: string;
}

/** PATCH /delivery/{id}/status uchun so'rov */
export interface DeliveryStatusUpdate {
  status: string;
  version: number;
  gps_lat?: number | null;
  gps_lng?: number | null;
  failure_reason?: string | null;
}

// ─── Paginated javob ──────────────────────────────────────────────────────────

export interface PaginatedDeliveries {
  items: Delivery[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Filtrlar ─────────────────────────────────────────────────────────────────

export interface DeliveryFilters {
  status?: string;
  courier_id?: string;
  order_id?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}
