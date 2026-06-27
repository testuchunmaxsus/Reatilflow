/**
 * Analytics feature tiplaari — ADR-004 ga mos.
 *
 * Korxona uchun do'kon-ombor intellekti:
 * - Shartnoma qilgan do'konlar holati
 * - Geo savdo tezligi (leaflet xarita)
 * - Expiry ogohlantirishlar (do'kon ombori)
 * - Mahsulot reytingi (top/bottom)
 * - AI tavsiyalar (rule-based + ixtiyoriy Claude)
 *
 * Maydon nomlari backend schemas.py bilan aynan mos (OverviewOut, ContractedStoreItem,
 * GeoVelocityItem, ExpiryItem, ProductRankingItem, RecommendationItem va ularning Out-lari).
 */

// ─── Filtr tipi ────────────────────────────────────────────────────────────────

export interface AnalyticsFilters {
  from?: string | null;
  to?: string | null;
}

export type ProductOrder = "top" | "bottom";

// ─── Overview ─────────────────────────────────────────────────────────────────

/** backend: ContractStatusCounts */
export interface ContractStatusCounts {
  active: number;
  expiring: number;
  expired: number;
}

/** backend: OverviewOut */
export interface OverviewOut {
  contracted_store_count: number;
  contract_status: ContractStatusCounts;
  sold_qty_total: number;   // Decimal → number (JSON serialisation)
  revenue_total: string;    // Decimal → string (toFixed precision)
  expiry_risk_count: number;
  period_from: string | null;
  period_to: string | null;
}

// ─── Contracted stores ─────────────────────────────────────────────────────────

/** backend: ContractedStoreItem */
export interface ContractedStoreItem {
  store_id: string;
  store_name: string;
  address: string | null;
  contract_status: "active" | "expiring" | "expired";
  valid_to: string;          // date → ISO string
  inventory_qty: number;    // Decimal → number
  sold_qty_30d: number;     // Decimal → number
  gps_lat: number | null;
  gps_lng: number | null;
}

/** backend: ContractedStoresOut */
export interface ContractedStoresOut {
  stores: ContractedStoreItem[];
  total: number;
}

// ─── Geo velocity ──────────────────────────────────────────────────────────────

/** backend: GeoVelocityItem */
export interface GeoVelocityItem {
  store_id: string;
  store_name: string;
  address: string | null;
  gps_lat: number | null;
  gps_lng: number | null;
  sold_qty: number;
  revenue: string;          // Decimal → string
  velocity_per_day: number;
}

/** backend: GeoVelocityOut */
export interface GeoVelocityOut {
  items: GeoVelocityItem[];
  period_from: string | null;
  period_to: string | null;
  period_days: number;
}

// ─── Expiry report ─────────────────────────────────────────────────────────────

export type ExpirySeverity = "expired" | "urgent" | "warning";

/** backend: ExpiryItem */
export interface ExpiryItem {
  inventory_id: string;
  store_id: string;
  store_name: string;
  product_id: string;
  product_name: string;
  qty: number;
  expiry_date: string;
  days_left: number;
  severity: ExpirySeverity;  // backend field is "severity", not "status"
}

/** backend: ExpiryReportOut */
export interface ExpiryReportOut {
  items: ExpiryItem[];
  total: number;
  within_days: number;
}

// ─── Product ranking ───────────────────────────────────────────────────────────

/** backend: ProductRankingItem */
export interface ProductRankingItem {
  product_id: string;
  product_name: string;
  sold_qty: number;
  revenue: string;          // Decimal → string
  store_count: number;
  rank: number;
}

/** backend: ProductRankingOut */
export interface ProductRankingOut {
  items: ProductRankingItem[];
  order: ProductOrder;
  period_from: string | null;
  period_to: string | null;
}

// ─── Recommendations ──────────────────────────────────────────────────────────

export type RecommendationSeverity = "high" | "medium" | "low" | "info";

/** backend: RecommendationItem */
export interface RecommendationItem {
  code: string;
  severity: RecommendationSeverity;
  title_uz: string;
  detail_uz: string;
  store_id?: string | null;
  product_id?: string | null;
  metric?: Record<string, unknown>;  // backend: dict
}

/** backend: RecommendationsOut */
export interface RecommendationsOut {
  recommendations: RecommendationItem[];
  ai_summary: string | null;
  ai_enabled: boolean;       // backend field is "ai_enabled", not "ai_enriched"
  generated_at: string;
}
