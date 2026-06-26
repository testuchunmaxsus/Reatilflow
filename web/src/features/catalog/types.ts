/**
 * Katalog feature tiplaari — CATALOG.md §2 ga mos.
 *
 * Asosiy tiplar `api/types.ts` da, bu yerda kengaytma va forma tiplaari.
 */

// Re-export qulaylik uchun
export type {
  CategoryOut,
  PriceSegmentOut,
  ProductOut,
  PriceHistoryOut,
} from "@/api/types";

// ─── Paginated javob ─────────────────────────────────────────────────────────

export interface PaginatedProducts {
  items: import("@/api/types").ProductOut[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Forma tiplaari (POST/PATCH) ──────────────────────────────────────────────

export interface ProductCreate {
  name_uz: string;
  name_ru: string;
  sku: string;
  barcode?: string | null;
  mxik_code?: string | null;
  unit: string;
  category_id?: string | null;
  is_active: boolean;
  branch_scope?: string | null;
  client_uuid?: string;
}

export interface ProductUpdate {
  name_uz?: string;
  name_ru?: string;
  sku?: string;
  barcode?: string | null;
  mxik_code?: string | null;
  unit?: string;
  category_id?: string | null;
  is_active?: boolean;
  branch_scope?: string | null;
  version: number; // optimistik lock — majburiy
}

// ─── Kategoriya yaratish ──────────────────────────────────────────────────────

export interface CategoryCreate {
  name_uz: string;
  name_ru?: string;
  parent_id?: string | null;
  is_active?: boolean;
}

// ─── Narx segmenti yaratish ───────────────────────────────────────────────────

export interface PriceSegmentCreate {
  name: string;
}

// ─── Narx o'rnatish ───────────────────────────────────────────────────────────

export interface SetPricePayload {
  segment_id: string;
  price: number;
  currency: "UZS";
  valid_from: string; // ISO date string
}
