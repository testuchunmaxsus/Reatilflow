/**
 * Davomat API — TanStack Query hook'lari.
 *
 * Endpointlar:
 *   GET /attendance   — paginated davomat ro'yxati
 *
 * RBAC (backend):
 *   attendance:view — agent, courier, administrator, accountant
 *   agent/courier: faqat o'z yozuvlari (IDOR himoya backend da)
 */

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type { PaginatedAttendance, AttendanceFilters } from "@/features/attendance/types";

// ─── Query keys ───────────────────────────────────────────────────────────────

export const attendanceKeys = {
  all: ["attendance"] as const,
  list: (filters?: AttendanceFilters) =>
    [...attendanceKeys.all, "list", filters ?? {}] as const,
};

// ─── Davomat ro'yxati ─────────────────────────────────────────────────────────

export function useAttendanceList(filters: AttendanceFilters = {}) {
  const params = new URLSearchParams();
  if (filters.user_id) params.set("user_id", filters.user_id);
  if (filters.date)    params.set("date", filters.date);
  params.set("limit",  String(filters.limit  ?? 20));
  params.set("offset", String(filters.offset ?? 0));
  const qs = params.toString();

  return useQuery({
    queryKey: attendanceKeys.list(filters),
    queryFn: () =>
      apiClient.get<PaginatedAttendance>(`/attendance?${qs}`),
    placeholderData: (prev) => prev,
  });
}
