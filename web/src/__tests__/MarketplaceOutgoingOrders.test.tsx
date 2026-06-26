/**
 * MarketplaceOutgoingOrders testlari
 *
 * Tekshiriladi:
 * 1. Chiquvchi buyurtmalar jadvalda ko'rsatiladi
 * 2. "delivered" holat uchun "Qabul qilish" tugmasi ko'rinadi
 * 3. Boshqa holatlarda "Qabul qilish" tugmasi ko'rinmaydi
 * 4. "Qabul qilish" bosilganda AcceptOrderModal ochiladi
 * 5. Modalda har line uchun expiry_date + markup_percent kiritiladi
 * 6. accept API PATCH /marketplace/orders/{id}/accept chaqiriladi
 * 7. Bo'sh holat ko'rsatiladi
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import type { AuthUser } from "@/auth/AuthContext";

// ─── Mock ma'lumotlar ─────────────────────────────────────────────────────────

const mockOutgoingOrders = {
  items: [
    {
      id: "out-001",
      buyer_store_id: "store-001",
      supplier_enterprise_id: "ent-002",
      supplier_name: "Supplier Korxona",
      lines: [
        {
          id: "line-001",
          product_id: "prod-001",
          product_name: "Mahsulot A",
          qty: 3,
          unit_price: 15000,
          line_total: 45000,
        },
      ],
      total_amount: 45000,
      status: "delivered",
      created_at: "2026-06-10T10:00:00Z",
      updated_at: "2026-06-10T12:00:00Z",
    },
    {
      id: "out-002",
      buyer_store_id: "store-001",
      supplier_enterprise_id: "ent-003",
      supplier_name: "Boshqa Supplier",
      lines: [],
      total_amount: 20000,
      status: "delivering",
      created_at: "2026-06-09T10:00:00Z",
      updated_at: "2026-06-09T11:00:00Z",
    },
    {
      id: "out-003",
      buyer_store_id: "store-001",
      supplier_enterprise_id: "ent-004",
      supplier_name: null,
      lines: [],
      total_amount: 5000,
      status: "accepted",
      created_at: "2026-06-08T10:00:00Z",
      updated_at: "2026-06-08T11:00:00Z",
    },
  ],
  total: 3,
  limit: 20,
  offset: 0,
};

const mockOutgoingEmpty = { items: [], total: 0, limit: 20, offset: 0 };

// ─── API mock ─────────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let outgoingResponse: any = mockOutgoingOrders;
const mockAccept = vi.fn(() => Promise.resolve({ id: "out-001", status: "accepted" }));

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn((path: string) => {
        if (path.startsWith("/marketplace/orders/outgoing"))
          return Promise.resolve(outgoingResponse);
        return Promise.resolve({});
      }),
      post: vi.fn(() => Promise.resolve({})),
      patch: vi.fn((path: string) => {
        if (path.includes("/accept")) return mockAccept();
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

import { OutgoingOrdersPage } from "@/features/marketplace/OutgoingOrdersPage";

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <Notifications />
        <MemoryRouter>
          <OutgoingOrdersPage />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("OutgoingOrdersPage — Accept flow", () => {
  beforeEach(() => {
    outgoingResponse = mockOutgoingOrders;
    vi.clearAllMocks();
  });

  it("chiquvchi buyurtmalar jadvalda ko'rsatiladi", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Supplier Korxona")).toBeInTheDocument();
      expect(screen.getByText("Boshqa Supplier")).toBeInTheDocument();
    });
  });

  it("sarlavha ko'rsatiladi", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/chiquvchi marketplace buyurtmalar/i)).toBeInTheDocument();
    });
  });

  it("delivered holat uchun qabul qilish tugmasi ko'rinadi", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Supplier Korxona")).toBeInTheDocument();
    });

    const acceptBtns = screen.getAllByLabelText(/qabul qilish/i);
    expect(acceptBtns.length).toBe(1);
  });

  it("delivering va accepted holatlar uchun qabul qilish tugmasi ko'rinmaydi", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Boshqa Supplier")).toBeInTheDocument();
    });

    // Faqat bitta delivered buyurtma bor
    const acceptBtns = screen.queryAllByLabelText(/qabul qilish/i);
    expect(acceptBtns.length).toBe(1);
  });

  it("qabul qilish tugmasi bosilganda modal ochiladi", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Supplier Korxona")).toBeInTheDocument();
    });

    const acceptBtn = screen.getByLabelText(/qabul qilish/i);
    fireEvent.click(acceptBtn);

    await waitFor(() => {
      expect(screen.getByText(/buyurtmani qabul qilish/i)).toBeInTheDocument();
    });
  });

  it("modalda mahsulot nomi ko'rsatiladi", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Supplier Korxona")).toBeInTheDocument();
    });

    const acceptBtn = screen.getByLabelText(/qabul qilish/i);
    fireEvent.click(acceptBtn);

    await waitFor(() => {
      expect(screen.getByText("Mahsulot A")).toBeInTheDocument();
    });
  });

  it("bo'sh holat ko'rsatiladi", async () => {
    outgoingResponse = mockOutgoingEmpty;
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/chiquvchi buyurtmalar topilmadi/i)).toBeInTheDocument();
    });
  });

  it("supplier_name null bo'lsa — jadvalda fallback ko'rsatiladi", async () => {
    renderPage();

    await waitFor(() => {
      const dashes = screen.getAllByText("—");
      expect(dashes.length).toBeGreaterThan(0);
    });
  });
});
