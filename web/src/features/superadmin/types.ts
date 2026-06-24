/**
 * Superadmin feature tiplaari — backend superadmin/schemas.py ga mos.
 */

// ─── Korxona ──────────────────────────────────────────────────────────────────

export interface SuperadminEnterpriseOut {
  id: string;
  name: string;
  inn: string | null;
  status: string; // "active" | "suspended"
  enabled_modules: string[];
  version: number;
  created_at: string;
  updated_at: string;
}

export interface SuperadminAdminOut {
  id: string;
  full_name: string;
  phone: string;
  role: string;
  locale: string;
  is_active: boolean;
  enterprise_id: string | null;
  created_at: string;
}

export interface SuperadminEnterpriseAdminOut {
  enterprise: SuperadminEnterpriseOut;
  admin: SuperadminAdminOut;
}

export interface SuperadminEnterprisePaginated {
  items: SuperadminEnterpriseOut[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Yaratish ─────────────────────────────────────────────────────────────────

export interface FirstAdminCreate {
  full_name: string;
  phone: string;
  password: string;
  locale: "uz" | "ru";
}

export interface EnterpriseCreate {
  name: string;
  inn?: string | null;
  enabled_modules: string[];
  first_admin: FirstAdminCreate;
}

// ─── Yangilash ────────────────────────────────────────────────────────────────

export interface EnterpriseUpdate {
  name?: string | null;
  enabled_modules?: string[] | null;
  status?: string | null;
  version: number;
}

// ─── Dashboard statistika ─────────────────────────────────────────────────────

export interface SuperadminStats {
  enterprises_total: int;
  enterprises_active: int;
  enterprises_suspended: int;
  users_total: int;
  enterprises_new_7d: int;
}

// TypeScript aliasi: backend int → TS number
type int = number;

// ─── Korxona tafsiloti ────────────────────────────────────────────────────────

/** GET /superadmin/enterprises/{id} javobi — adminlar + user_count bilan */
export interface SuperadminEnterpriseDetailAdmin {
  id: string;
  full_name: string;
  phone: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface SuperadminEnterpriseDetail extends SuperadminEnterpriseOut {
  user_count: number;
  admins: SuperadminEnterpriseDetailAdmin[];
}

// ─── Parol reset ──────────────────────────────────────────────────────────────

export interface ResetAdminPasswordRequest {
  user_id: string;
  new_password?: string | null;
}

export interface ResetAdminPasswordResponse {
  user_id: string;
  new_password: string;
}

// ─── Cross-tenant foydalanuvchilar ────────────────────────────────────────────

export interface SuperadminUserOut {
  id: string;
  full_name: string;
  phone: string;
  role: string;
  is_active: boolean;
  enterprise_id: string | null;
  enterprise_name: string | null;
  created_at: string;
}

export interface SuperadminUserPaginated {
  items: SuperadminUserOut[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Ro'yxat filtrlari ────────────────────────────────────────────────────────

export interface EnterpriseListFilters {
  search?: string;
  status?: string;
  limit?: number;
  offset?: number;
}
