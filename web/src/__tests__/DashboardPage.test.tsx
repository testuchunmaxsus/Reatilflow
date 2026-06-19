/**
 * DashboardPage testlari
 *
 * Tekshiriladi:
 * 1. Sahifa sarlavhasi va xush kelibsiz matni render bo'ladi
 * 2. Do'konlar soni (customers:view) ko'rsatiladi
 * 3. Mahsulotlar soni (catalog:view) ko'rsatiladi
 * 4. Foydalanuvchilar soni (rbac:view) ko'rsatiladi
 * 5. Savdo statistikasi (stats:view) ko'rsatiladi
 * 6. Moliyaviy balans (finance:view) ko'rsatiladi
 * 7. Agent — finance:view yo'q, moliyaviy karta ko'rinmaydi
 * 8. Agent — rbac:view yo'q, foydalanuvchilar kartasi ko'rinmaydi
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import type { AuthUser } from "@/auth/AuthContext";
import { DashboardPage } from "@/pages/DashboardPage";

// ─── Mock ma'lumotlar ─────────────────────────────────────────────────────────

const mockStores = { items: [], total: 42, limit: 1, offset: 0 };
const mockProducts = { items: [], total: 155, limit: 1, offset: 0 };
const mockUsers = { items: [], total: 8, limit: 1, offset: 0 };
const mockSales = {
  total_orders: 320,
  total_amount: "7500000.00",
  currency: "UZS",
  period_from: null,
  period_to: null,
  group_by: null,
  dynamics: [],
};
const mockFinance = {
  total_debit: "10000000.00",
  total_credit: "6000000.00",
  net_balance: "4000000.00",
  stores: [],
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
        if (path.startsWith("/customers/stores")) return Promise.resolve(mockStores);
        if (path.startsWith("/catalog/products")) return Promise.resolve(mockProducts);
        if (path.startsWith("/users")) return Promise.resolve(mockUsers);
        if (path.includes("/stats/sales")) return Promise.resolve(mockSales);
        if (path.includes("/stats/finance")) return Promise.resolve(mockFinance);
        return Promise.resolve({});
      }),
      post: vi.fn(() => Promise.resolve({})),
      patch: vi.fn(() => Promise.resolve({})),
      delete: vi.fn(() => Promise.resolve(undefined)),
    },
  };
});

// ─── Foydalanuvchilar ─────────────────────────────────────────────────────────

const adminUser: AuthUser = {
  id: "admin-001",
  phone: "+998901234567",
  full_name: "Ibrohim Karimov",
  role: "administrator",
  branch_id: null,
  locale: "uz",
  is_active: true,
  biometric_enrolled: false,
  permissions: [
    "customers:view",
    "catalog:view",
    "rbac:view",
    "stats:view",
    "finance:view",
  ],
};

const agentUser: AuthUser = {
  id: "agent-001",
  phone: "+998901234568",
  full_name: "Sardor Toshev",
  role: "agent",
  branch_id: null,
  locale: "uz",
  is_active: true,
  biometric_enrolled: false,
  // agent: finance:view yo'q, rbac:view yo'q
  permissions: ["customers:view", "catalog:view", "stats:view"],
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

function renderDashboard(user: AuthUser = adminUser) {
  currentUser = user;
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <Notifications />
        <MemoryRouter>
          <DashboardPage />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("DashboardPage", () => {
  beforeEach(() => {
    currentUser = adminUser;
    vi.clearAllMocks();
  });

  it("sahifa sarlavhasi render bo'ladi", () => {
    renderDashboard(adminUser);
    expect(screen.getByText("Bosh sahifa")).toBeInTheDocument();
  });

  it("xush kelibsiz matni ism va rol bilan ko'rsatiladi", () => {
    renderDashboard(adminUser);
    expect(screen.getByText(/Ibrohim Karimov/)).toBeInTheDocument();
    expect(screen.getByText(/Administrator/i)).toBeInTheDocument();
  });

  it("do'konlar soni ko'rsatiladi (customers:view)", async () => {
    renderDashboard(adminUser);
    await waitFor(() => {
      expect(screen.getByText("Jami do'konlar")).toBeInTheDocument();
      expect(screen.getByText("42")).toBeInTheDocument();
    });
  });

  it("mahsulotlar soni ko'rsatiladi (catalog:view)", async () => {
    renderDashboard(adminUser);
    await waitFor(() => {
      expect(screen.getByText("Jami mahsulotlar")).toBeInTheDocument();
      expect(screen.getByText("155")).toBeInTheDocument();
    });
  });

  it("foydalanuvchilar soni ko'rsatiladi (rbac:view)", async () => {
    renderDashboard(adminUser);
    await waitFor(() => {
      expect(screen.getByText("Jami foydalanuvchilar")).toBeInTheDocument();
      expect(screen.getByText("8")).toBeInTheDocument();
    });
  });

  it("savdo statistikasi ko'rsatiladi (stats:view)", async () => {
    renderDashboard(adminUser);
    await waitFor(() => {
      expect(screen.getByText("Buyurtmalar soni")).toBeInTheDocument();
      expect(screen.getByText("320")).toBeInTheDocument();
      // Summa formatlangan
      expect(screen.getByText(/7\s*500\s*000.*UZS/)).toBeInTheDocument();
    });
  });

  it("moliyaviy balans ko'rsatiladi (finance:view)", async () => {
    renderDashboard(adminUser);
    await waitFor(() => {
      expect(screen.getByText("Moliyaviy balans")).toBeInTheDocument();
      // net_balance musbat → Haqdor
      expect(screen.getByText(/Haqdor/i)).toBeInTheDocument();
    });
  });

  it("agent: rbac:view yo'q — foydalanuvchilar kartasi ko'rinmaydi", async () => {
    renderDashboard(agentUser);
    await waitFor(() => {
      // do'konlar va mahsulotlar ko'rinishi kerak
      expect(screen.getByText("Jami do'konlar")).toBeInTheDocument();
    });
    expect(screen.queryByText("Jami foydalanuvchilar")).not.toBeInTheDocument();
  });

  it("agent: finance:view yo'q — moliyaviy karta ko'rinmaydi", async () => {
    renderDashboard(agentUser);
    await waitFor(() => {
      expect(screen.getByText("Buyurtmalar soni")).toBeInTheDocument();
    });
    expect(screen.queryByText("Moliyaviy balans")).not.toBeInTheDocument();
  });
});
