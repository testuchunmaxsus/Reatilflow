/**
 * Analytics feature tiplaari — ADR-004 ga mos.
 *
 * Korxona uchun do'kon-ombor intellekti:
 * - Shartnoma qilgan do'konlar holati
 * - Geo savdo tezligi (leaflet xarita)
 * - Expiry ogohlantirishlar (do'kon ombori)
 * - Mahsulot reytingi (top/bottom)
 * - AI tavsiyalar (rule-based + ixtiyoriy Claude)
 */

// ─── Filtr tipi ────────────────────────────────────────────────────────────────

export interface AnalyticsFilters {
  from?: string | null;
  to?: string | null;
}

export type ProductOrder = "top" | "bottom";

// ─── Overview ─────────────────────────────────────────────────────────────────

export interface OverviewOut {
  contracted_stores_count: number;
  active_contracts: number;
  expiring_contracts: number;
  expired_contracts: number;
  total_sold_qty: number;
  total_revenue: string;
  expiry_risk_sku_count: number;
  top_product_id: string | null;
  top_product_name: string | null;
  period_from: string | null;
  period_to: string | null;
}

// ─── Contracted stores ─────────────────────────────────────────────────────────

export interface ContractedStoreItem {
  store_id: string;
  store_name: string;
  address: string | null;
  contract_status: "active" | "expiring" | "expired";
  valid_to: string | null;
  inventory_qty: number;
  sold_qty_30d: number;
  revenue_30d: string;
}

export interface ContractedStoresOut {
  stores: ContractedStoreItem[];
  total: number;
}

// ─── Geo velocity ──────────────────────────────────────────────────────────────

export interface GeoVelocityItem {
  store_id: string;
  store_name: string;
  address: string | null;
  lat: number | null;
  lng: number | null;
  sold_qty: number;
  revenue: string;
  velocity_per_day: number;
}

export interface GeoVelocityOut {
  stores: GeoVelocityItem[];
  period_from: string | null;
  period_to: string | null;
  period_days: number;
}

// ─── Expiry report ─────────────────────────────────────────────────────────────

export type ExpiryStatus = "expired" | "urgent" | "warning";

export interface ExpiryItem {
  store_id: string;
  store_name: string;
  product_id: string;
  product_name: string;
  qty: number;
  expiry_date: string;
  days_left: number;
  status: ExpiryStatus;
}

export interface ExpiryReportOut {
  items: ExpiryItem[];
  total: number;
  within_days: number;
}

// ─── Product ranking ───────────────────────────────────────────────────────────

export interface ProductRankItem {
  product_id: string;
  product_name: string;
  sold_qty: number;
  revenue: string;
  store_count: number;
}

export interface ProductRankingOut {
  products: ProductRankItem[];
  order: ProductOrder;
  period_from: string | null;
  period_to: string | null;
}

// ─── Recommendations ──────────────────────────────────────────────────────────

export type RecommendationSeverity = "high" | "medium" | "low";

export interface RecommendationItem {
  code: string;
  severity: RecommendationSeverity;
  title_uz: string;
  detail_uz: string;
  store_id?: string | null;
  product_id?: string | null;
  metric?: number | null;
}

export interface RecommendationsOut {
  recommendations: RecommendationItem[];
  ai_enriched: boolean;
  ai_summary: string | null;
  generated_at: string;
}
