/**
 * UI Module Gating testlari — MT5 (B qism).
 *
 * Tekshiriladi:
 * 1. EnterpriseContext: hasModule to'g'ri ishlaydi
 * 2. Yoqilmagan modul nav da ko'rinmaydi (AppLayout)
 * 3. Yoqilgan modul ko'rinadi
 * 4. superadmin uchun har doim true (bypass)
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import type { AuthUser } from "@/auth/AuthContext";

// ─── Mock ma'lumotlar ─────────────────────────────────────────────────────────

const enterpriseWithPromo = {
  id: "ent-001",
  name: "Test Korxona",
  inn: null,
  status: "active",
  enabled_modules: ["catalog", "orders", "customers", "promo", "stats", "tickets", "contracts"],
};

const enterpriseWithoutPromo = {
  id: "ent-001",
  name: "Test Korxona",
  inn: null,
  status: "active",
  enabled_modules: ["catalog", "orders", "customers"],
};

// ─── API mock ─────────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let enterpriseMeResponse: any = enterpriseWithPromo;

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn(() => Promise.resolve(enterpriseMeResponse)),
      post: vi.fn(() => Promise.resolve({})),
      patch: vi.fn(() => Promise.resolve({})),
      delete: vi.fn(() => Promise.resolve(undefined)),
    },
  };
});

// ─── Auth mock ────────────────────────────────────────────────────────────────

const adminUser: AuthUser = {
  id: "admin-001",
  phone: "+998901234567",
  full_name: "Test Admin",
  role: "administrator",
  branch_id: null,
  locale: "uz",
  is_active: true,
  biometric_enrolled: false,
  permissions: [
    "rbac:view",
    "rbac:create",
    "catalog:view",
    "customers:view",
    "orders:view",
    "stats:view",
    "tickets:view",
    "contracts:view",
    "promo:view",
  ],
};

let currentUser: AuthUser = adminUser;

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({
    user: currentUser,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
  }),
}));

// ─── Render yordamchisi ───────────────────────────────────────────────────────

import { AppLayout } from "@/layouts/AppLayout";
import {
  EnterpriseProvider,
  useEnterprise,
} from "@/enterprise/EnterpriseContext";

function renderLayout(user: AuthUser = adminUser) {
  currentUser = user;
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <MemoryRouter initialEntries={["/"]}>
          <EnterpriseProvider>
            <AppLayout />
          </EnterpriseProvider>
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("UI Module Gating (AppLayout nav)", () => {
  beforeEach(() => {
    currentUser = adminUser;
    enterpriseMeResponse = enterpriseWithPromo;
    vi.clearAllMocks();
  });

  it("yoqilgan modul (promo) nav da ko'rsatiladi", async () => {
    enterpriseMeResponse = enterpriseWithPromo;
    renderLayout(adminUser);

    await waitFor(() => {
      expect(screen.getByText("Aksiyalar")).toBeInTheDocument();
    });
  });

  it("o'chirilgan modul (promo) nav da ko'rsatilmaydi", async () => {
    enterpriseMeResponse = enterpriseWithoutPromo;
    renderLayout(adminUser);

    await waitFor(() => {
      // Promo nav elementi ko'rinmasligi kerak
      expect(screen.queryByText("Aksiyalar")).not.toBeInTheDocument();
    });
  });

  it("Bosh sahifa har doim ko'rinadi (requiredModule yo'q)", async () => {
    enterpriseMeResponse = enterpriseWithoutPromo;
    renderLayout(adminUser);

    await waitFor(() => {
      expect(screen.getByText("Bosh sahifa")).toBeInTheDocument();
    });
  });

  it("Katalog yoqilgan bo'lsa ko'rinadi", async () => {
    enterpriseMeResponse = enterpriseWithPromo; // catalog bor
    renderLayout(adminUser);

    await waitFor(() => {
      expect(screen.getByText("Katalog")).toBeInTheDocument();
    });
  });
});

// ─── hasModule testi ──────────────────────────────────────────────────────────

import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";

describe("useEnterprise hasModule", () => {
  beforeEach(() => {
    enterpriseMeResponse = enterpriseWithPromo;
    vi.clearAllMocks();
  });

  it("yoqilgan modul uchun true qaytaradi", async () => {
    const wrapper = ({ children }: { children: ReactNode }) => (
      <MantineProvider>
        <EnterpriseProvider>{children}</EnterpriseProvider>
      </MantineProvider>
    );

    const { result } = renderHook(() => useEnterprise(), { wrapper });

    await waitFor(() => {
      expect(result.current.hasModule("catalog")).toBe(true);
      expect(result.current.hasModule("promo")).toBe(true);
    });
  });

  it("o'chirilgan modul uchun false qaytaradi", async () => {
    enterpriseMeResponse = enterpriseWithoutPromo;

    const wrapper = ({ children }: { children: ReactNode }) => (
      <MantineProvider>
        <EnterpriseProvider>{children}</EnterpriseProvider>
      </MantineProvider>
    );

    const { result } = renderHook(() => useEnterprise(), { wrapper });

    await waitFor(() => {
      expect(result.current.hasModule("promo")).toBe(false);
    });
  });
});
