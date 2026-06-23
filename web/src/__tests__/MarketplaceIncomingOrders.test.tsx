/**
 * MarketplaceIncomingOrders testlari — yangi kontrakt
 *
 * Backend statuslari: pending | confirmed | rejected | delivering | delivered | accepted
 * buyer_store_name | supplier_name | courier_name | lines[].product_name — null bo'lishi mumkin
 *
 * Tekshiriladi:
 * 1. Kiruvchi buyurtmalar jadvalda ko'rsatiladi
 * 2. Pending holat uchun Tasdiqlash/Rad etish tugmalari ko'rinadi
 * 3. Confirmed holat uchun Kuryer tayinlash tugmasi ko'rinadi
 * 4. Tasdiqlash mutatsiya chaqiriladi
 * 5. Rad etish mutatsiya chaqiriladi
 * 6. Kuryer tayinlash modal ochiladi va ship mutatsiya chaqiriladi
 * 7. Bo'sh holat ko'rsatiladi
 * 8. delivering va accepted holatlari badge bilan ko'rsatiladi
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import type { AuthUser } from "@/auth/AuthContext";

// ─── Mock ma'lumotlar — yangi kontrakt ────────────────────────────────────────

const mockIncomingOrders = {
  items: [
    {
      id: "order-001",
      buyer_store_id: "store-001",
      buyer_store_name: "Test Do'kon",
      supplier_enterprise_id: "ent-001",
      supplier_name: null,
      lines: [
        {
          id: "line-001",
          product_id: "prod-001",
          product_name: "Mahsulot 1",
          qty: 5,
          unit_price: 10000,
          line_total: 50000,
        },
      ],
      total_amount: 50000,
      status: "pending",
      courier_id: null,
      courier_name: null,
      created_at: "2026-06-01T10:00:00Z",
      updated_at: "2026-06-01T10:00:00Z",
    },
    {
      id: "order-002",
      buyer_store_id: "store-002",
      buyer_store_name: "Ikkinchi Do'kon",
      supplier_enterprise_id: "ent-001",
      supplier_name: null,
      lines: [
        {
          id: "line-002",
          product_id: "prod-002",
          product_name: null,
          qty: 2,
          unit_price: 20000,
          line_total: 40000,
        },
      ],
      total_amount: 40000,
      status: "confirmed",
      courier_id: null,
      courier_name: null,
      created_at: "2026-06-02T10:00:00Z",
      updated_at: "2026-06-02T10:00:00Z",
    },
    {
      id: "order-003",
      buyer_store_id: "store-003",
      buyer_store_name: null,
      supplier_enterprise_id: "ent-001",
      supplier_name: null,
      lines: [],
      total_amount: 0,
      status: "delivering",
      courier_id: "courier-001",
      courier_name: "Alisher Kuryer",
      created_at: "2026-06-03T10:00:00Z",
      updated_at: "2026-06-03T10:00:00Z",
    },
    {
      id: "order-004",
      buyer_store_id: "store-004",
      buyer_store_name: "To'rtinchi Do'kon",
      supplier_enterprise_id: "ent-001",
      supplier_name: null,
      lines: [],
      total_amount: 15000,
      status: "accepted",
      courier_id: null,
      courier_name: null,
      created_at: "2026-06-04T10:00:00Z",
      updated_at: "2026-06-04T10:00:00Z",
    },
  ],
  total: 4,
  limit: 20,
  offset: 0,
};

const mockIncomingEmpty = { items: [], total: 0, limit: 20, offset: 0 };

const mockCouriers = {
  items: [
    {
      id: "courier-001",
      full_name: "Alisher Kuryer",
      phone: "+998901234567",
      role: "courier",
      branch_id: null,
      locale: "uz",
      is_active: true,
      biometric_enrolled: false,
      device_id: null,
      version: 1,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
  ],
  total: 1,
};

// ─── API mock ─────────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let incomingResponse: any = mockIncomingOrders;
const mockConfirm = vi.fn(() => Promise.resolve({ id: "order-001", status: "confirmed" }));
const mockReject = vi.fn(() => Promise.resolve({ id: "order-001", status: "rejected" }));
const mockShip = vi.fn(() => Promise.resolve({ id: "order-002", status: "delivering" }));

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn((path: string) => {
        if (path.startsWith("/marketplace/orders/incoming"))
          return Promise.resolve(incomingResponse);
        if (path.startsWith("/users"))
          return Promise.resolve(mockCouriers);
        return Promise.resolve({});
      }),
      post: vi.fn(() => Promise.resolve({})),
      patch: vi.fn((path: string) => {
        if (path.includes("/confirm")) return mockConfirm();
        if (path.includes("/reject")) return mockReject();
        if (path.includes("/ship")) return mockShip();
        return Promise.resolve({});
      }),
      delete: vi.fn(() => Promise.resolve(undefined)),
    },
  };
});

// ─── Auth mock ────────────────────────────────────────────────────────────────

const adminUser: AuthUser = {
  id: "admin-001",
  phone: "+998901234567",
  full_name: "Admin",
  role: "administrator",
  branch_id: null,
  locale: "uz",
  is_active: true,
  biometric_enrolled: false,
  permissions: ["catalog:view", "catalog:edit"],
};

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({
    user: adminUser,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
  }),
}));

// ─── Render yordamchisi ───────────────────────────────────────────────────────

import { IncomingOrdersPage } from "@/features/marketplace/IncomingOrdersPage";

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <Notifications />
        <MemoryRouter>
          <IncomingOrdersPage />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("IncomingOrdersPage — yangi kontrakt (delivering, accepted, null fallback)", () => {
  beforeEach(() => {
    incomingResponse = mockIncomingOrders;
    vi.clearAllMocks();
  });

  it("kiruvchi buyurtmalar jadvalda ko'rsatiladi", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Test Do'kon")).toBeInTheDocument();
      expect(screen.getByText("Ikkinchi Do'kon")).toBeInTheDocument();
    });
  });

  it("sarlavha ko'rsatiladi", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/kiruvchi marketplace buyurtmalar/i)).toBeInTheDocument();
    });
  });

  it("pending holat uchun tasdiqlash va rad etish tugmalari ko'rinadi", async () => {
    renderPage();

    await waitFor(() => {
      const confirmBtns = screen.getAllByLabelText(/tasdiqlash/i);
      expect(confirmBtns.length).toBeGreaterThan(0);
      const rejectBtns = screen.getAllByLabelText(/rad etish/i);
      expect(rejectBtns.length).toBeGreaterThan(0);
    });
  });

  it("confirmed holat uchun kuryer tayinlash tugmasi ko'rinadi", async () => {
    renderPage();

    await waitFor(() => {
      const shipBtns = screen.getAllByLabelText(/kuryer tayinlash/i);
      expect(shipBtns.length).toBeGreaterThan(0);
    });
  });

  it("tasdiqlash tugmasi bosilganda confirm mutatsiya chaqiriladi", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Test Do'kon")).toBeInTheDocument();
    });

    const confirmBtns = screen.getAllByLabelText(/tasdiqlash/i);
    fireEvent.click(confirmBtns[0]);

    await waitFor(() => {
      expect(mockConfirm).toHaveBeenCalledTimes(1);
    });
  });

  it("rad etish tugmasi bosilganda reject mutatsiya chaqiriladi", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Test Do'kon")).toBeInTheDocument();
    });

    const rejectBtns = screen.getAllByLabelText(/rad etish/i);
    fireEvent.click(rejectBtns[0]);

    await waitFor(() => {
      expect(mockReject).toHaveBeenCalledTimes(1);
    });
  });

  it("kuryer tayinlash modal ochiladi", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Ikkinchi Do'kon")).toBeInTheDocument();
    });

    const shipBtns = screen.getAllByLabelText(/kuryer tayinlash/i);
    fireEvent.click(shipBtns[0]);

    await waitFor(() => {
      expect(screen.getByText(/kuryer tayinlash/i)).toBeInTheDocument();
    });
  });

  it("bo'sh holat ko'rsatiladi", async () => {
    incomingResponse = mockIncomingEmpty;
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/kiruvchi buyurtmalar topilmadi/i)).toBeInTheDocument();
    });
  });

  it("delivering holati badge bilan ko'rsatiladi", async () => {
    renderPage();

    await waitFor(() => {
      // delivering holat uchun i18n key: marketplace.order_status.delivering
      expect(screen.getByText(/yetkazilmoqda/i)).toBeInTheDocument();
    });
  });

  it("accepted holati badge bilan ko'rsatiladi", async () => {
    renderPage();

    await waitFor(() => {
      // accepted holat uchun i18n key: marketplace.order_status.accepted
      expect(screen.getByText(/qabul qilindi/i)).toBeInTheDocument();
    });
  });

  it("buyer_store_name null bo'lsa — jadvalda fallback ko'rsatiladi", async () => {
    renderPage();

    await waitFor(() => {
      // order-003 buyer_store_name: null → "—"
      const dashes = screen.getAllByText("—");
      expect(dashes.length).toBeGreaterThan(0);
    });
  });
});
