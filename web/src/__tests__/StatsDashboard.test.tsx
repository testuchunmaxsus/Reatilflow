/**
 * StatsDashboardPage testlari
 *
 * Tekshiriladi:
 * 1. Sahifa sarlavhasi render bo'ladi
 * 2. Savdo bo'limi kartalari ko'rsatiladi (mock data)
 * 3. Grafik render bo'ladi (recharts)
 * 4. Yetkazish bo'limi ko'rsatiladi
 * 5. Moliyaviy bo'lim — buxgalter/admin ko'radi (finance:view)
 * 6. Moliyaviy bo'lim — kuryer ko'rmaydi (finance:view yo'q)
 * 7. Moliyaviy jadvaldagi do'kon qarz/haqdorlik to'g'ri ko'rsatiladi
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import type { AuthUser } from "@/auth/AuthContext";
import { StatsDashboardPage } from "@/features/stats/StatsDashboardPage";

// ─── Mock ma'lumotlar ─────────────────────────────────────────────────────────

const mockSalesStats = {
  total_orders: 42,
  total_amount: "1850000.00",
  currency: "UZS",
  period_from: "2026-06-01T00:00:00",
  period_to: "2026-06-30T23:59:59",
  group_by: "day",
  dynamics: [
    { period: "2026-06-15", order_count: 18, total_amount: "820000.00" },
    { period: "2026-06-16", order_count: 24, total_amount: "1030000.00" },
  ],
};

const mockDeliveryStats = {
  total_deliveries: 30,
  delivered_count: 25,
  failed_count: 2,
  in_progress_count: 3,
  avg_delivery_minutes: "47.50",
  period_from: "2026-06-01T00:00:00",
  period_to: null,
};

const mockFinanceStats = {
  total_debit: "5000000.00",
  total_credit: "3200000.00",
  net_balance: "1800000.00",
  stores: [
    {
      store_id: "store-001",
      store_name: "Yunusobod Supermarket",
      total_debit: "3000000.00",
      total_credit: "2000000.00",
      balance: "1000000.00",
      currency: "UZS",
    },
    {
      store_id: "store-002",
      store_name: "Chilonzor Market",
      total_debit: "2000000.00",
      total_credit: "1200000.00",
      balance: "-200000.00",
      currency: "UZS",
    },
  ],
  period_from: null,
  period_to: null,
};

// ─── API mock ─────────────────────────────────────────────────────────────────

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn((path: string) => {
        if (path.includes("/stats/sales")) return Promise.resolve(mockSalesStats);
        if (path.includes("/stats/delivery")) return Promise.resolve(mockDeliveryStats);
        if (path.includes("/stats/finance")) return Promise.resolve(mockFinanceStats);
        return Promise.resolve({});
      }),
      post: vi.fn(() => Promise.resolve({})),
      patch: vi.fn(() => Promise.resolve({})),
      delete: vi.fn(() => Promise.resolve(undefined)),
    },
    getAccessToken: vi.fn(() => null),
  };
});

// ─── Foydalanuvchilar ─────────────────────────────────────────────────────────

const adminUser: AuthUser = {
  id: "admin-001",
  phone: "+998901234567",
  full_name: "Admin",
  role: "administrator",
  branch_id: null,
  locale: "uz",
  is_active: true,
  biometric_enrolled: false,
  permissions: ["stats:view", "finance:view", "orders:view"],
};

const accountantUser: AuthUser = {
  id: "accountant-001",
  phone: "+998901234569",
  full_name: "Accountant",
  role: "accountant",
  branch_id: null,
  locale: "uz",
  is_active: true,
  biometric_enrolled: false,
  permissions: ["stats:view", "finance:view"],
};

const courierUser: AuthUser = {
  id: "courier-001",
  phone: "+998901234570",
  full_name: "Courier",
  role: "courier",
  branch_id: null,
  locale: "uz",
  is_active: true,
  biometric_enrolled: false,
  // courier: finance:view yo'q (RBAC.md matritsasi)
  permissions: ["stats:view", "delivery:view"],
};

// ─── useAuth mock ─────────────────────────────────────────────────────────────

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

function renderStatsDashboard(user: AuthUser = adminUser) {
  currentUser = user;
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <Notifications />
        <MemoryRouter>
          <StatsDashboardPage />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("StatsDashboardPage", () => {
  beforeEach(() => {
    currentUser = adminUser;
    vi.clearAllMocks();
  });

  it("sahifa sarlavhasi render bo'ladi", () => {
    renderStatsDashboard(adminUser);
    expect(screen.getByText("Statistika")).toBeInTheDocument();
  });

  it("savdo bo'limi sarlavhasi ko'rsatiladi", async () => {
    renderStatsDashboard(adminUser);
    await waitFor(() => {
      expect(screen.getByText("Savdo statistikasi")).toBeInTheDocument();
    });
  });

  it("savdo kartalari (jami buyurtmalar, summa) ko'rsatiladi", async () => {
    renderStatsDashboard(adminUser);
    await waitFor(() => {
      expect(screen.getByText("Jami buyurtmalar")).toBeInTheDocument();
      expect(screen.getByText("42")).toBeInTheDocument();
      expect(screen.getByText("Jami summa")).toBeInTheDocument();
    });
  });

  it("savdo grafik container mavjud", async () => {
    renderStatsDashboard(adminUser);
    await waitFor(() => {
      // Grafik sarlavhasi
      expect(screen.getByText("Savdo dinamikasi")).toBeInTheDocument();
    });
  });

  it("yetkazish bo'limi ma'lumotlari ko'rsatiladi", async () => {
    renderStatsDashboard(adminUser);
    await waitFor(() => {
      expect(screen.getByText("Yetkazish statistikasi")).toBeInTheDocument();
      expect(screen.getByText("Jami yetkazishlar")).toBeInTheDocument();
      expect(screen.getByText("30")).toBeInTheDocument();
    });
  });

  it("yetkazish o'rtacha vaqt ko'rsatiladi", async () => {
    renderStatsDashboard(adminUser);
    await waitFor(() => {
      expect(screen.getByText("O'rtacha vaqt")).toBeInTheDocument();
      expect(screen.getByText(/47\.50/)).toBeInTheDocument();
    });
  });

  it("buxgalter moliyaviy bo'limni ko'radi (finance:view bor)", async () => {
    renderStatsDashboard(accountantUser);
    await waitFor(() => {
      expect(screen.getByText("Moliyaviy statistika")).toBeInTheDocument();
      expect(screen.getByText("Yunusobod Supermarket")).toBeInTheDocument();
    });
  });

  it("admin moliyaviy jadvaldagi do'konlarni ko'radi", async () => {
    renderStatsDashboard(adminUser);
    await waitFor(() => {
      expect(screen.getByText("Yunusobod Supermarket")).toBeInTheDocument();
      expect(screen.getByText("Chilonzor Market")).toBeInTheDocument();
    });
  });

  it("kuryer moliyaviy bo'limni ko'rmaydi (finance:view yo'q)", async () => {
    renderStatsDashboard(courierUser);
    // Savdo va yetkazish bo'limlari yuklanishini kutamiz
    await waitFor(() => {
      expect(screen.getByText("Savdo statistikasi")).toBeInTheDocument();
    });
    // Moliyaviy bo'lim sarlavhasi ko'rinmasligi kerak
    expect(
      screen.queryByText("Moliyaviy statistika"),
    ).not.toBeInTheDocument();
    // Do'kon nomi ham ko'rinmasligi kerak
    expect(
      screen.queryByText("Yunusobod Supermarket"),
    ).not.toBeInTheDocument();
  });

  it("qarzdor do'kon 'Qarzdor' badge bilan ko'rinadi", async () => {
    renderStatsDashboard(adminUser);
    await waitFor(() => {
      expect(screen.getAllByText("Qarzdor").length).toBeGreaterThan(0);
    });
  });

  it("group_by select mavjud", async () => {
    renderStatsDashboard(adminUser);
    await waitFor(() => {
      expect(screen.getByText("Guruhlash")).toBeInTheDocument();
    });
  });
});
