/**
 * Marketplace tiplaari — korxona-admin boshqaruvi.
 *
 * Kiruvchi buyurtmalar (supplier sifatida):
 *   GET  /marketplace/orders/incoming
 *   PATCH /marketplace/orders/{id}/confirm
 *   PATCH /marketplace/orders/{id}/reject
 *   PATCH /marketplace/orders/{id}/ship  (courier_id bilan)
 *
 * Chiquvchi buyurtmalar (xaridor sifatida):
 *   GET  /marketplace/orders/outgoing
 *
 * Mahsulot publish toggle:
 *   PATCH /catalog/products/{id}/marketplace
 *
 * Bannerlar:
 *   GET    /marketplace/banners/mine
 *   POST   /marketplace/banners
 *   PATCH  /marketplace/banners/{id}
 *   DELETE /marketplace/banners/{id}
 *
 * Aksiya featured toggle:
 *   PATCH /promos/{id}/marketplace-featured
 */

// ─── Marketplace buyurtma holatlari ──────────────────────────────────────────

export type MarketplaceOrderStatus =
  | "pending"
  | "confirmed"
  | "rejected"
  | "delivering"
  | "delivered"
  | "accepted";

// ─── Buyurtma qatori ──────────────────────────────────────────────────────────

export interface MarketplaceOrderLine {
  id: string;
  product_id: string;
  product_name: string | null;
  qty: number;
  unit_price: number;
  line_total: number;
}

// ─── Kiruvchi buyurtma (supplier uchun) ──────────────────────────────────────

export interface IncomingOrder {
  id: string;
  buyer_store_id: string;
  buyer_store_name: string | null;
  supplier_enterprise_id: string;
  supplier_name: string | null;
  lines: MarketplaceOrderLine[];
  total_amount: number;
  status: MarketplaceOrderStatus;
  courier_id: string | null;
  courier_name: string | null;
  created_at: string;
  updated_at: string;
}

// ─── Chiquvchi buyurtma (xaridor uchun) ──────────────────────────────────────

export interface OutgoingOrder {
  id: string;
  buyer_store_id: string;
  supplier_enterprise_id: string;
  supplier_name: string | null;
  lines: MarketplaceOrderLine[];
  total_amount: number;
  status: MarketplaceOrderStatus;
  created_at: string;
  updated_at: string;
}

// ─── Sahifalash ───────────────────────────────────────────────────────────────

export interface PaginatedIncomingOrders {
  items: IncomingOrder[];
  total: number;
  limit: number;
  offset: number;
}

export interface PaginatedOutgoingOrders {
  items: OutgoingOrder[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Banner ───────────────────────────────────────────────────────────────────

export interface BannerOut {
  id: string;
  enterprise_id: string;
  title: string;
  image_url: string | null;
  target_url: string | null;
  target_product_id: string | null;
  is_active: boolean;
  priority: number;
  valid_from: string;
  valid_to: string;
  created_at: string;
  updated_at: string;
}

export interface BannerCreate {
  title: string;
  target_url?: string | null;
  target_product_id?: string | null;
  is_active?: boolean;
  priority?: number;
  valid_from: string;
  valid_to: string;
}

export interface BannerUpdate {
  title?: string;
  target_url?: string | null;
  target_product_id?: string | null;
  is_active?: boolean;
  priority?: number;
  valid_from?: string;
  valid_to?: string;
}

export interface PaginatedBanners {
  items: BannerOut[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Mahsulot marketplace publish ─────────────────────────────────────────────

export interface MarketplacePublishPayload {
  marketplace_published: boolean;
  marketplace_price?: number | null;
}

// ─── Aksiya featured toggle ───────────────────────────────────────────────────

export interface MarketplaceFeaturedPayload {
  featured: boolean;
}

// ─── Buyurtmani qabul qilish ──────────────────────────────────────────────────

export interface AcceptOrderLinePayload {
  line_id: string;
  /** ISO sana: YYYY-MM-DD */
  expiry_date: string;
  /** 0+ foiz (masalan 15.5) */
  markup_percent: number;
}

export interface AcceptOrderPayload {
  lines: AcceptOrderLinePayload[];
}

// ─── Buyurtmani rad etish ─────────────────────────────────────────────────────

export interface RejectOrderPayload {
  /** Ixtiyoriy, max 500 belgi */
  reason?: string;
}

// ─── Filtrlar ─────────────────────────────────────────────────────────────────

export interface OrderFilters {
  status?: string;
  limit?: number;
  offset?: number;
}
