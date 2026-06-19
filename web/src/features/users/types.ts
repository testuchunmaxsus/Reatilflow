/**
 * Foydalanuvchilar feature tiplaari — backend schemas.py ga mos.
 *
 * Backend endpointlari (users/router.py):
 *   GET    /users              — PaginatedUsers
 *   POST   /users              — UserOut (201)
 *   GET    /users/{id}         — UserOut
 *   PATCH  /users/{id}         — UserOut (optimistik lock: version majburiy)
 *   PATCH  /users/{id}/deactivate — UserOut
 */

export type UserRole =
  | "administrator"
  | "agent"
  | "courier"
  | "accountant"
  | "store";

// ─── Javob ────────────────────────────────────────────────────────────────────

export interface UserOut {
  id: string;
  full_name: string;
  /** PII — admin ko'radi */
  phone: string;
  role: UserRole;
  branch_id: string | null;
  locale: "uz" | "ru";
  biometric_enrolled: boolean;
  device_id: string | null;
  is_active: boolean;
  version: number;
  created_at: string;
  updated_at: string;
}

// ─── Paginated ────────────────────────────────────────────────────────────────

export interface PaginatedUsers {
  items: UserOut[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Yaratish ─────────────────────────────────────────────────────────────────

export interface UserCreate {
  full_name: string;
  phone: string;
  role: UserRole;
  branch_id?: string | null;
  locale?: "uz" | "ru";
  password: string;
  biometric_enrolled?: boolean;
  device_id?: string | null;
}

// ─── Yangilash (PATCH) ────────────────────────────────────────────────────────

export interface UserUpdate {
  full_name?: string;
  phone?: string;
  role?: UserRole;
  branch_id?: string | null;
  locale?: "uz" | "ru";
  version: number; // optimistik lock — majburiy
}

// ─── Filtrlar ─────────────────────────────────────────────────────────────────

export interface UserFilters {
  role?: UserRole;
  branch_id?: string;
  is_active?: boolean;
  limit?: number;
  offset?: number;
}
