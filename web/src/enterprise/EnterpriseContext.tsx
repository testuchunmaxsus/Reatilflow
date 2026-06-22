/**
 * EnterpriseContext — joriy korxona holati (enabled_modules).
 *
 * Xususiyatlar:
 * - Login qilinganda /enterprise/me chaqirib enabled_modules oladi.
 * - superadmin (enterprise_id yo'q) uchun null holat (modullar yo'q tekshiruv).
 * - enabled_modules UX gating uchun (nav filtrlash, route guard).
 *   Haqiqiy autorizatsiya BACKEND tomonidan bajariladi.
 *
 * Foydalanish:
 *   const { enabledModules, hasModule } = useEnterprise();
 *   if (!hasModule("promo")) return null;
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { apiClient } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";

// ─── Tiplar ───────────────────────────────────────────────────────────────────

export interface EnterpriseInfo {
  id: string;
  name: string;
  inn: string | null;
  status: string;
  enabled_modules: string[];
}

export interface EnterpriseContextValue {
  /** null = yuklanmoqda yoki superadmin; undefined = xato */
  enterprise: EnterpriseInfo | null | undefined;
  isLoading: boolean;
  /** Modul yoqilganligini tekshiradi. superadmin uchun har doim true (bypass). */
  hasModule: (moduleKey: string) => boolean;
  /** enabled_modules ro'yxati yangilanganda kontekstni qayta yuklaydi */
  refreshEnterprise: () => Promise<void>;
}

// ─── Kontekst ─────────────────────────────────────────────────────────────────

const EnterpriseContext = createContext<EnterpriseContextValue | undefined>(undefined);

// ─── Provider ─────────────────────────────────────────────────────────────────

interface EnterpriseProviderProps {
  children: ReactNode;
}

export function EnterpriseProvider({ children }: EnterpriseProviderProps) {
  const { user, isLoading: authLoading } = useAuth();
  const [enterprise, setEnterprise] = useState<EnterpriseInfo | null | undefined>(null);
  const [isLoading, setIsLoading] = useState(false);

  const loadEnterprise = useCallback(async (): Promise<void> => {
    // superadmin → enterprise yo'q, bypass
    if (!user || user.role === "superadmin") {
      setEnterprise(null);
      return;
    }

    setIsLoading(true);
    try {
      const data = await apiClient.get<EnterpriseInfo>("/enterprise/me");
      setEnterprise(data);
    } catch {
      // 404 — superadmin holat yoki boshqa xato
      setEnterprise(null);
    } finally {
      setIsLoading(false);
    }
  }, [user]);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      setEnterprise(null);
      return;
    }
    void loadEnterprise();
  }, [user, authLoading, loadEnterprise]);

  const hasModule = useCallback(
    (moduleKey: string): boolean => {
      // superadmin — barcha modul bypass
      if (user?.role === "superadmin") return true;
      // Yuklanmagan holatda — ruxsat yo'q (fail-closed UX)
      if (!enterprise) return false;
      return enterprise.enabled_modules.includes(moduleKey);
    },
    [user, enterprise],
  );

  const refreshEnterprise = useCallback(async (): Promise<void> => {
    await loadEnterprise();
  }, [loadEnterprise]);

  return (
    <EnterpriseContext.Provider
      value={{ enterprise, isLoading, hasModule, refreshEnterprise }}
    >
      {children}
    </EnterpriseContext.Provider>
  );
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useEnterprise(): EnterpriseContextValue {
  const ctx = useContext(EnterpriseContext);
  if (!ctx) {
    throw new Error("useEnterprise: EnterpriseProvider tashqarisida ishlatilmoqda");
  }
  return ctx;
}
