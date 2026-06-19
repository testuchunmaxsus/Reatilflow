/**
 * usePermissions — joriy foydalanuvchi ruxsatlarini qaytaradi.
 *
 * MUHIM: Bu faqat UX maqsadida — UI elementlarini yashirish/ko'rsatish uchun.
 * Haqiqiy autorizatsiya BACKEND tomonidan bajariladi.
 */

import { useAuth } from "@/auth/AuthContext";
import type { UserRole } from "@/api/types";

export interface UsePermissionsResult {
  role: UserRole | undefined;
  permissions: Set<string>;
  /** "module:action" mavjudligini tekshiradi */
  can: (permission: string) => boolean;
  /** Modulga biror ruxsat borligini tekshiradi */
  canAny: (module: string, actions: string[]) => boolean;
}

export function usePermissions(): UsePermissionsResult {
  const { user } = useAuth();

  const permSet = new Set<string>(user?.permissions ?? []);

  const can = (permission: string): boolean => {
    if (!user) return false;
    return permSet.has(permission);
  };

  const canAny = (module: string, actions: string[]): boolean => {
    if (!user) return false;
    return actions.some((action) => permSet.has(`${module}:${action}`));
  };

  return {
    role: user?.role,
    permissions: permSet,
    can,
    canAny,
  };
}
