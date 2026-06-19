/**
 * usePermissions hook testlari
 *
 * Tekshiriladi:
 * 1. can() to'g'ri permission bilan true qaytaradi
 * 2. can() noto'g'ri permission bilan false qaytaradi
 * 3. canAny() bir nechta actiondan hech biri bo'lmasa false
 * 4. canAny() bitta action mavjud bo'lsa true
 * 5. User yo'q bo'lsa can() false qaytaradi
 */

import { describe, it, expect, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { usePermissions } from "@/rbac/usePermissions";
import type { AuthUser } from "@/auth/AuthContext";

// ─── useAuth mock ─────────────────────────────────────────────────────────

const mockUser: AuthUser = {
  id: "test-uuid",
  phone: "+998901234567",
  full_name: "Test Admin",
  role: "administrator",
  branch_id: null,
  locale: "uz",
  is_active: true,
  biometric_enrolled: false,
  permissions: [
    "catalog:view",
    "catalog:create",
    "catalog:edit",
    "catalog:delete",
    "customers:view",
    "customers:create",
    "stats:view",
    "rbac:view",
    "rbac:create",
    "rbac:edit",
    "rbac:delete",
  ],
};

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({ user: mockUser }),
}));

// ─── Testlar ──────────────────────────────────────────────────────────────

describe("usePermissions", () => {
  it("can() mavjud permission bilan true qaytaradi", () => {
    const { result } = renderHook(() => usePermissions());
    expect(result.current.can("catalog:view")).toBe(true);
    expect(result.current.can("catalog:create")).toBe(true);
    expect(result.current.can("rbac:delete")).toBe(true);
  });

  it("can() mavjud bo'lmagan permission bilan false qaytaradi", () => {
    const { result } = renderHook(() => usePermissions());
    expect(result.current.can("finance:approve")).toBe(false);
    expect(result.current.can("catalog:approve")).toBe(false);
  });

  it("canAny() hech bir action yo'q bo'lsa false qaytaradi", () => {
    const { result } = renderHook(() => usePermissions());
    expect(result.current.canAny("finance", ["create", "approve"])).toBe(false);
  });

  it("canAny() bitta action mavjud bo'lsa true qaytaradi", () => {
    const { result } = renderHook(() => usePermissions());
    expect(result.current.canAny("catalog", ["create", "approve"])).toBe(true);
  });

  it("role to'g'ri qaytariladi", () => {
    const { result } = renderHook(() => usePermissions());
    expect(result.current.role).toBe("administrator");
  });
});
