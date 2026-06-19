/**
 * Auth konteksti — autentifikatsiya holati va amallari.
 *
 * Arxitektura:
 * - access_token: xotirada (React state), hech qachon localStorage/sessionStorage'ga
 *   yozilmaydi — XSS dan xavfsiz
 * - refresh_token: localStorage'da — XSS tradeoff. Tauri desktop/veb SPA uchun
 *   httpOnly cookie ishlatib bo'lmaydi (cross-origin yoki Tauri ipc). Production
 *   veb deployda httpOnly cookie bilan almashtirish tavsiya etiladi.
 * - permissions: /auth/me javobidan olinadi, xotirada saqlanadi
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  apiClient,
  clearTokens,
  getRefreshToken,
  setTokens,
} from "@/api/client";
import type { LoginRequest, MeResponse, TokenPair, UserRole } from "@/api/types";

// ─── Tiplar ───────────────────────────────────────────────────────────────

export interface AuthUser {
  id: string;
  phone: string;
  full_name: string;
  role: UserRole;
  branch_id: string | null;
  locale: "uz" | "ru";
  is_active: boolean;
  biometric_enrolled: boolean;
  /** "module:action" ro'yxati */
  permissions: string[];
}

export interface AuthContextValue {
  /** null — hali yuklanmagan; undefined — autentifikatsiya yo'q */
  user: AuthUser | null | undefined;
  isLoading: boolean;
  login: (credentials: LoginRequest) => Promise<void>;
  logout: () => Promise<void>;
  /** Hozirgi foydalanuvchi ma'lumotlarini qayta yuklab oladi */
  refreshUser: () => Promise<void>;
}

// ─── Kontekst ─────────────────────────────────────────────────────────────

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

// ─── Provider ─────────────────────────────────────────────────────────────

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  /** null = yuklanayapti, undefined = login kerak, AuthUser = kirgan */
  const [user, setUser] = useState<AuthUser | null | undefined>(null);
  const [isLoading, setIsLoading] = useState(true);
  // Initializatsiya faqat bir marta ishlashi uchun
  const initDone = useRef(false);

  // /auth/me dan foydalanuvchini yuklab olish
  const loadUser = useCallback(async (): Promise<void> => {
    try {
      const me = await apiClient.get<MeResponse>("/auth/me");
      setUser({
        id: me.id,
        phone: me.phone,
        full_name: me.full_name,
        role: me.role,
        branch_id: me.branch_id,
        locale: me.locale,
        is_active: me.is_active,
        biometric_enrolled: me.biometric_enrolled,
        permissions: me.permissions ?? [],
      });
    } catch {
      // 401 — token yo'q yoki muddati o'tgan
      setUser(undefined);
    }
  }, []);

  // Ilova ishga tushganda localStorage'da refresh token bor bo'lsa qayta tiklash
  useEffect(() => {
    if (initDone.current) return;
    initDone.current = true;

    const savedRefresh = getRefreshToken();
    if (!savedRefresh) {
      setUser(undefined);
      setIsLoading(false);
      return;
    }

    // access token xotirada yo'q, lekin refresh bor — yangi access token olamiz
    apiClient
      .post<TokenPair>("/auth/refresh", { refresh_token: savedRefresh }, { skipAuth: true })
      .then((pair) => {
        setTokens(pair);
        return loadUser();
      })
      .catch(() => {
        clearTokens();
        setUser(undefined);
      })
      .finally(() => setIsLoading(false));
  }, [loadUser]);

  // client.ts tomonidan yuboriladigan global logout event
  useEffect(() => {
    const handler = () => {
      setUser(undefined);
    };
    window.addEventListener("retail:auth:logout", handler);
    return () => window.removeEventListener("retail:auth:logout", handler);
  }, []);

  const login = useCallback(
    async (credentials: LoginRequest): Promise<void> => {
      const pair = await apiClient.post<TokenPair>(
        "/auth/login",
        credentials,
        { skipAuth: true },
      );
      setTokens(pair);
      await loadUser();
    },
    [loadUser],
  );

  const logout = useCallback(async (): Promise<void> => {
    const refreshToken = getRefreshToken();
    if (refreshToken) {
      try {
        await apiClient.post("/auth/logout", { refresh_token: refreshToken });
      } catch {
        // Logout xatosi kritik emas — lokaldan token'larni har holatda tozalaymiz
      }
    }
    clearTokens();
    setUser(undefined);
  }, []);

  const refreshUser = useCallback(async (): Promise<void> => {
    await loadUser();
  }, [loadUser]);

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

// ─── Hook ─────────────────────────────────────────────────────────────────

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth: AuthProvider tashqarisida ishlatilmoqda");
  }
  return ctx;
}
