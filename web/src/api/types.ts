/**
 * API tiplaari — qo'lda yozilgan minimal to'plam.
 *
 * Bu fayl `make gen-client` bilan `openapi.gen.ts` dan to'ldiriladi.
 * Hozircha backend `/openapi.json` dan generatsiya qilinguncha minimal tiplar shu yerda.
 *
 * Generatsiya: `npm run gen-types` yoki `make gen-client` (backend/Makefile).
 */

// ─── Auth ──────────────────────────────────────────────────────────────────

export interface LoginRequest {
  phone: string;
  password: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
}

export interface RefreshRequest {
  refresh_token: string;
}

export interface LogoutRequest {
  refresh_token: string;
}

/**
 * Rol qiymatlari — ADR-001 §3.6, RBAC.md
 * MT5: "superadmin" roli qo'shildi.
 */
export type UserRole =
  | "superadmin"
  | "administrator"
  | "agent"
  | "courier"
  | "accountant"
  | "store";

/**
 * /auth/me javobi (T2 kengaytmasi: permissions maydoni bilan)
 */
export interface MeResponse {
  id: string;
  phone: string;
  full_name: string;
  role: UserRole;
  branch_id: string | null;
  locale: "uz" | "ru";
  is_active: boolean;
  biometric_enrolled: boolean;
  /** RBAC ruxsatlar ro'yxati (T2 dan). Format: "module:action" */
  permissions?: string[];
}

// ─── Xato envelope ─────────────────────────────────────────────────────────

/**
 * Barcha backend xato javoblari shu formatda keladi (I18N.md §3).
 */
export interface ErrorEnvelope {
  message_key: string;
  message: string;
  detail: unknown | null;
}

// ─── Katalog ───────────────────────────────────────────────────────────────

export interface CategoryOut {
  id: string;
  name_uz: string;
  name_ru: string;
  parent_id: string | null;
  is_active: boolean;
}

export interface ProductOut {
  id: string;
  name_uz: string;
  name_ru: string;
  sku: string;
  barcode: string | null;
  mxik_code: string | null;
  unit: string;
  category_id: string;
  photo_url: string | null;
  is_active: boolean;
  branch_scope: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface PriceSegmentOut {
  id: string;
  name: string;
}

export interface ProductPriceOut {
  id: string;
  product_id: string;
  segment_id: string;
  price: number;
  currency: string;
  valid_from: string;
  valid_to: string | null;
}

// ─── Mijoz (Do'kon) ────────────────────────────────────────────────────────

export interface StoreOut {
  id: string;
  name: string;
  /** PII — pgcrypto bilan shifrlangan, faqat administrator/buxgalter ko'radi */
  inn: string | null;
  inps: string | null;
  /** PII — kuryer (StoreLimitedOut) da mavjud emas */
  owner_name: string | null;
  phone: string | null;
  gps_lat: string | null;
  gps_lng: string | null;
  address: string | null;
  segment_id: string | null;
  agent_id: string | null;
  branch_id: string | null;
  credit_limit: string | null;
  user_id?: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  deleted_at?: string | null;
}

// ─── Foydalanuvchi ─────────────────────────────────────────────────────────

export interface AppUserOut {
  id: string;
  full_name: string;
  phone: string;
  role: UserRole;
  branch_id: string | null;
  locale: "uz" | "ru";
  is_active: boolean;
  biometric_enrolled: boolean;
  device_id: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

// ─── Sahifalash ────────────────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

// ─── Katalog (narx tarixi) ─────────────────────────────────────────────────────

export interface PriceHistoryOut {
  id: string;
  product_id: string;
  segment_id: string;
  old_price: string | null;
  new_price: string;
  currency: string;
  changed_by: string;
  changed_at: string;
}

// ─── Statistika ────────────────────────────────────────────────────────────

// Statistika tiplaari features/stats/types.ts da aniqlangan.
// Bu yerda qayta eksport kerak emas — features to'g'ridan-to'g'ri ishlatadi.

// ─── RBAC ──────────────────────────────────────────────────────────────────

export interface MyPermissionsResponse {
  role: UserRole;
  permissions: string[];
  total: number;
}

export interface CheckPermissionResponse {
  module: string;
  action: string;
  allowed: boolean;
  role: UserRole;
}
