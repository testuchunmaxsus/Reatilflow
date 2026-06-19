/**
 * AuthContext — test uchun eksport.
 * Testlar AuthContext.Provider dan foydalanish uchun.
 */

// AuthContext ni to'g'ridan-to'g'ri eksport qilish uchun internal shaklda saqlash
import { createContext } from "react";
import type { AuthContextValue } from "../AuthContext";

// Qayta ishlatiluvchi test mock context
export const AuthContext = createContext<AuthContextValue>({
  user: undefined,
  isLoading: false,
  login: async () => {},
  logout: async () => {},
  refreshUser: async () => {},
});
