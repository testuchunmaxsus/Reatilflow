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

// ─── Marketplace browse (cross-tenant katalog) ────────────────────────────────

/** GET /marketplace/products — bitta mahsulot javobi */
export interface MarketplaceProductOut {
  id: string;
  name_uz: string;
  name_ru: string;
  /** Lokalizatsiyalangan nom (backend joriy Accept-Language bo'yicha) */
  name: string;
  sku: string | null;
  barcode: string | null;
  unit: string;
  category_id: string | null;
  photo_url: string | null;
  is_active: boolean;
  marketplace_published: boolean;
  marketplace_price: number | null;
  /** Ko'rsatiladigan narx: marketplace_price yoki segment narxi */
  price: number | null;
  supplier_enterprise_id: string;
  supplier_name: string;
  created_at: string;
  updated_at: string;
}

/** GET /marketplace/products — paginated javob */
export interface PaginatedMarketplaceProducts {
  items: MarketplaceProductOut[];
  total: number;
  limit: number;
  offset: number;
}

/** GET /marketplace/suppliers — bitta supplier */
export interface MarketplaceSupplierOut {
  enterprise_id: string;
  name: string;
  product_count: number;
}

/** POST /marketplace/orders — bitta qator */
export interface MarketplaceOrderLineCreate {
  product_id: string;
  qty: number;
}

/**
 * POST /marketplace/orders tanasi.
 * lines: barcha mahsulotlar bir supplierdan bo'lishi shart.
 * buyer_store_id: ixtiyoriy (store roli uchun avtomatik).
 * client_uuid: idempotentlik (ixtiyoriy).
 */
export interface MarketplaceOrderCreate {
  lines: MarketplaceOrderLineCreate[];
  buyer_store_id?: string | null;
  client_uuid?: string | null;
}

/** Marketplace mahsulot browse filtrlari */
export interface MarketplaceBrowseFilters {
  search?: string;
  supplier_enterprise?: string;
  page?: number;
  limit?: number;
}
