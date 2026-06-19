/**
 * Statistika feature tiplaari — STATS.md ga mos.
 */

// ─── Savdo statistikasi ────────────────────────────────────────────────────────

export type GroupBy = "day" | "week" | "month";

export interface SalesPeriodItem {
  period: string;
  order_count: number;
  total_amount: string;
}

export interface SalesStatsOut {
  total_orders: number;
  total_amount: string;
  currency: string;
  period_from: string | null;
  period_to: string | null;
  group_by: GroupBy | null;
  dynamics: SalesPeriodItem[];
}

// ─── Yetkazish statistikasi ────────────────────────────────────────────────────

export interface DeliveryStatsOut {
  total_deliveries: number;
  delivered_count: number;
  failed_count: number;
  in_progress_count: number;
  avg_delivery_minutes: string | null;
  period_from: string | null;
  period_to: string | null;
}

// ─── Moliyaviy statistika ─────────────────────────────────────────────────────

export interface FinanceStoreItem {
  store_id: string;
  store_name: string;
  total_debit: string;
  total_credit: string;
  balance: string;
  currency: string;
}

export interface FinanceStatsOut {
  total_debit: string;
  total_credit: string;
  net_balance: string;
  stores: FinanceStoreItem[];
  period_from: string | null;
  period_to: string | null;
}

// ─── Filtr tipi ────────────────────────────────────────────────────────────────

export interface StatsFilters {
  from?: string | null;
  to?: string | null;
  group_by?: GroupBy | null;
  branch_id?: string | null;
  courier_id?: string | null;
}
