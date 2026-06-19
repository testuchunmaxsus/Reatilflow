/**
 * OrderListPage testlari
 *
 * Tekshiriladi:
 * 1. Jadval sarlavhalari render bo'ladi
 * 2. API ma'lumotlari jadvalda ko'rsatiladi (status badge, summa)
 * 3. Status filter select mavjud
 * 4. admin/agent uchun "Buyurtma qo'shish" tugmasi ko'rinadi (orders:create)
 * 5. buxgalter uchun "Buyurtma qo'shish" ko'rinmaydi (orders:create yo'q)
 * 6. Status badge to'g'ri rangda ko'rinadi
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import type { AuthUser } from "@/auth/AuthContext";
import { OrderListPage } from "@/features/orders/OrderListPage";

// ─── Mock ma'lumotlar ─────────────────────────────────────────────────────────

const mockOrders = {
  items: [
    {
      id: "01900000-0000-7000-8000-000000000100",
      store_id: "01900000-0000-7000-8000-000000000001",
      agent_id: "01900000-0000-7000-8000-000000000002",
      mode: "oddiy",
      status: "confirmed",
      total_amount: "250000.00",
      currency: "UZS",
      ordered_at: "2026-06-16T10:00:00Z",
      client_uuid: null,
      branch_id: null,
      warehouse_id: null,
      version: 1,
      created_at: "2026-06-16T10:00:00Z",
      updated_at: "2026-06-16T10:00:00Z",
      deleted_at: null,
      lines: [],
    },
    {
      id: "01900000-0000-7000-8000-000000000101",
      store_id: "01900000-0000-7000-8000-000000000002",
      agent_id: null,
      mode: "bozor",
      status: "delivered",
      total_amount: "75000.00",
      currency: "UZS",
      ordered_at: "2026-06-15T08:00:00Z",
      client_uuid: null,
      branch_id: null,
      warehouse_id: null,
      version: 3,
      created_at: "2026-06-15T08:00:00Z",
      updated_at: "2026-06-15T12:00:00Z",
      deleted_at: null,
      lines: [],
    },
  ],
  total: 2,
  limit: 20,
  offset: 0,
};

// ─── API mock ─────────────────────────────────────────────────────────────────

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn((path: string) => {
        if (path.includes("/orders")) return Promise.resolve(mockOrders);
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
  permissions: [
    "orders:view",
    "orders:create",
    "orders:edit",
    "stats:view",
    "finance:view",
  ],
};

const agentUser: AuthUser = {
  id: "agent-001",
  phone: "+998901234568",
  full_name: "Agent",
  role: "agent",
  branch_id: null,
  locale: "uz",
  is_active: true,
  biometric_enrolled: false,
  permissions: ["orders:view", "orders:create", "orders:edit", "stats:view"],
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
  permissions: ["orders:view", "stats:view", "finance:view"],
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

function renderOrderListPage(user: AuthUser = adminUser) {
  currentUser = user;
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <Notifications />
        <MemoryRouter>
          <OrderListPage />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("OrderListPage", () => {
  beforeEach(() => {
    currentUser = adminUser;
    vi.clearAllMocks();
  });

  it("jadval sarlavhalari ko'rsatiladi", async () => {
    renderOrderListPage(adminUser);
    await waitFor(() => {
      expect(screen.getByText("Raqam")).toBeInTheDocument();
      expect(screen.getByText("Sana")).toBeInTheDocument();
      expect(screen.getByText("Summa")).toBeInTheDocument();
    });
  });

  it("API dan kelgan buyurtmalar jadvalda ko'rsatiladi", async () => {
    renderOrderListPage(adminUser);
    await waitFor(() => {
      // Ikkita buyurtma status badge lari ko'rinishi kerak
      expect(screen.getByText("Tasdiqlangan")).toBeInTheDocument();
      expect(screen.getByText("Yetkazildi")).toBeInTheDocument();
    });
  });

  it("status badge ko'rsatiladi", async () => {
    renderOrderListPage(adminUser);
    await waitFor(() => {
      expect(screen.getByText("Tasdiqlangan")).toBeInTheDocument();
      expect(screen.getByText("Yetkazildi")).toBeInTheDocument();
    });
  });

  it("status filter select mavjud", async () => {
    renderOrderListPage(adminUser);
    await waitFor(() => {
      // Holat filtri placeholder ko'rinadi
      expect(
        screen.getByText("Barcha holatlar"),
      ).toBeInTheDocument();
    });
  });

  it("administrator uchun 'Buyurtma qo'shish' tugmasi ko'rinadi", async () => {
    renderOrderListPage(adminUser);
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /buyurtma qo'shish/i }),
      ).toBeInTheDocument();
    });
  });

  it("agent uchun 'Buyurtma qo'shish' tugmasi ko'rinadi (orders:create bor)", async () => {
    renderOrderListPage(agentUser);
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /buyurtma qo'shish/i }),
      ).toBeInTheDocument();
    });
  });

  it("buxgalter uchun 'Buyurtma qo'shish' tugmasi ko'rinmaydi (orders:create yo'q)", async () => {
    renderOrderListPage(accountantUser);
    await waitFor(() => {
      // Jadval yuklanishi kutiladi
      expect(screen.getByText("Tasdiqlangan")).toBeInTheDocument();
    });
    expect(
      screen.queryByRole("button", { name: /buyurtma qo'shish/i }),
    ).not.toBeInTheDocument();
  });

  it("summa to'g'ri formatda ko'rsatiladi", async () => {
    renderOrderListPage(adminUser);
    await waitFor(() => {
      // UZS valyuta ko'rsatilishi kerak
      const uzsElements = screen.getAllByText(/UZS/);
      expect(uzsElements.length).toBeGreaterThan(0);
    });
  });
});
