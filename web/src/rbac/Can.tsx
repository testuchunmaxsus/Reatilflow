/**
 * <Can> komponenti — ruxsat bo'lmasa ichidagi elementni yashiradi.
 *
 * MUHIM: Bu faqat UX maqsadida. Haqiqiy autorizatsiya backend'da.
 *
 * Foydalanish:
 *   <Can permission="catalog:create">
 *     <Button>Mahsulot qo'shish</Button>
 *   </Can>
 *
 *   <Can permission="finance:approve" fallback={<Text c="dimmed">Ruxsat yo'q</Text>}>
 *     <ApproveButton />
 *   </Can>
 */

import type { ReactNode } from "react";
import { usePermissions } from "./usePermissions";

interface CanProps {
  /** "module:action" formatida ruxsat, masalan "catalog:create" */
  permission: string;
  children: ReactNode;
  /** Ruxsat bo'lmaganda ko'rsatiladigan element (default: null — hech narsa) */
  fallback?: ReactNode;
}

export function Can({ permission, children, fallback = null }: CanProps) {
  const { can } = usePermissions();

  if (!can(permission)) {
    return <>{fallback}</>;
  }

  return <>{children}</>;
}
