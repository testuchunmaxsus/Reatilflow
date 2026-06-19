/**
 * useDebounce — qiymatni kechiktirish uchun hook.
 *
 * Foydalanish:
 *   const debouncedSearch = useDebounce(searchInput, 300);
 */

import { useEffect, useState } from "react";

export function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}

/**
 * i18n alias — faqat string uchun qulaylik.
 */
export function useI18nDebounce(value: string, delay: number): string {
  return useDebounce(value, delay);
}
