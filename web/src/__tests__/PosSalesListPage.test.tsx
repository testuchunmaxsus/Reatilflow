/**
 * PosSalesListPage smoke testi.
 *
 * Tekshiriladi:
 * 1. Sotuvlar jadvali ko'rsatiladi
 * 2. Summary kartalari ko'rsatiladi (kunlik jami)
 * 3. pos:create ruxsati bilan "Yangi sotuv" tugmasi ko'rinadi
 * 4. pos:create ruxsatisiz "Yangi sotuv" tugmasi ko'rinmaydi
 * 5. Bo'sh holat ko'rsatiladi
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import type { AuthUser } from "@/auth/AuthContext";

// ─── Mock ma'lumotlar ────────────────────────────────────────────────────────

const mockSummary = {
  date: "2026-06-24",
  total_sales: 5,
  total_amount: "500000",
  by_payment: [
    { payment_method: "cash", count: 3, total_amount: "300000" },
    { payment_method: "card", count: 2, total_amount: "200000" },
  ],
};

const mockSales = {
  items: [
    {
      id: "sale-001",
      store_id: "store-001",
      cashier_id: "user-001",
      enterprise_id: "ent-001",
      total_amount: "150000",
      discount_amount: "0",
      payment_method: "cash",
      customer_phone: null,
      status: "completed",
      client_uuid: null,
      created_at: "2026-06-24T10:00:00Z",
      lines: [
        {
          id: "line-001",
          product_id: "prod-001",
          qty: "2",
          unit_price: "75000",
          line_total: "150000",
        },
      ],
    },
  ],
  total: 1,
  limit: 20,
  offset: 0,
};

const mockSalesEmpty = { items: [], total: 0, limit: 20, offset: 0 };

// ─── API mock ─────────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let salesResponse: any = mockSales;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let summaryResponse: any = mockSummary;

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn((path: string) => {
        if (path.startsWith("/pos/sales")) return Promise.resolve(salesResponse);
        if (path.startsWith("/pos/summary")) return Promise.resolve(summaryResponse);
        return Promise.resolve({});
      }),
      post: vi.fn(() => Promise.resolve({})),
      patch: vi.fn(() => Promise.resolve({})),
      delete: vi.fn(() => Promise.resolve(undefined)),
    },
  };
});

// ─── Auth mock ────────────────────────────────────────────────────────────────

let mockUser: AuthUser = {
  id: "user-001",
  phone: "+998901234567",
  full_name: "Kassir",
  role: "store",
  branch_id: "store-001",
  locale: "uz",
  is_active: true,
  biometric_enrolled: false,
  permissions: ["pos:create", "pos:view"],
};

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({
    user: mockUser,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
  }),
}));

// ─── Render yordamchisi ───────────────────────────────────────────────────────

import { PosSalesListPage } from "@/features/pos/PosSalesListPage";

function renderPage(onNewSale?: () => void) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <Notifications />
        <MemoryRouter>
          <PosSalesListPage onNewSale={onNewSale} />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("PosSalesListPage — smoke testi", () => {
  beforeEach(() => {
    salesResponse = mockSales;
    summaryResponse = mockSummary;
    mockUser = {
      id: "user-001",
      phone: "+998901234567",
      full_name: "Kassir",
      role: "store",
      branch_id: "store-001",
      locale: "uz",
      is_active: true,
      biometric_enrolled: false,
      permissions: ["pos:create", "pos:view"],
    };
    vi.clearAllMocks();
  });

  it("sahifa sarlavhasi va jami summary kartalari ko'rsatiladi", async () => {
    renderPage();

    await waitFor(() => {
      // Title
      expect(screen.getByText(/POS/i)).toBeInTheDocument();
      // Summary karta: 5 sotuv
      expect(screen.getByText("5")).toBeInTheDocument();
    });
  });

  it("sotuvlar jadvali ko'rsatiladi", async () => {
    renderPage();

    await waitFor(() => {
      // Sana ustuni mavjud
      expect(screen.getByRole("columnheader", { name: /sana/i })).toBeInTheDocument();
      // Kamida bitta satr bor (payment badge topiladi)
      const badges = screen.getAllByText(/naqd/i);
      expect(badges.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("pos:create ruxsati bilan 'Yangi sotuv' tugmasi ko'rinadi", async () => {
    renderPage();

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /yangi sotuv/i }),
      ).toBeInTheDocument();
    });
  });

  it("pos:create ruxsatisiz 'Yangi sotuv' tugmasi ko'rinmaydi", async () => {
    mockUser = { ...mockUser, permissions: ["pos:view"] };
    renderPage();

    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: /yangi sotuv/i }),
      ).not.toBeInTheDocument();
    });
  });

  it("bo'sh sotuvlar holati ko'rsatiladi", async () => {
    salesResponse = mockSalesEmpty;
    renderPage();

    await waitFor(() => {
      expect(
        screen.getByText(/bugun sotuvlar yo'q/i),
      ).toBeInTheDocument();
    });
  });
});
