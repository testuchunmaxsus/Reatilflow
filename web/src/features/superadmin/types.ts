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
