import { useState } from "react";

/**
 * usePagination — server-side sahifalash uchun umumiy hook.
 *
 * Foydalanish:
 *   const { page, setPage, offset, pageSize, getTotalPages, resetPage } = usePagination(20);
 *
 * @param pageSize — sahifadagi elementlar soni (standart: 20)
 */
export function usePagination(pageSize = 20) {
  const [page, setPage] = useState(1);
  const offset = (page - 1) * pageSize;

  const getTotalPages = (total: number | undefined | null) =>
    total ? Math.max(1, Math.ceil(total / pageSize)) : 1;

  const resetPage = () => setPage(1);

  return { page, setPage, offset, pageSize, getTotalPages, resetPage };
}
