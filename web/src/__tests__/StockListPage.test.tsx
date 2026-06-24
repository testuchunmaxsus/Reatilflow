/**
 * StockListPage smoke testi.
 *
 * Tekshiriladi:
 * 1. Harakatlar jadvalda ko'rsatiladi (ID, tur, miqdor)
 * 2. Sahifa sarlavhasi ko'rsatiladi
 * 3. stock:create ruxsati bilan "Harakat qo'shish" tugmasi ko'rinadi
 * 4. Bo'sh holat ko'rsatiladi
 * 5. Harakat qo'shish tugmasi bosilganda modal ochiladi
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import type { AuthUser } from "@/auth/AuthContext";

// ─── Mock ma'lumotlar ─────────────────────────────────────────────────────────

const mockMovements = {
  items: [
    {
      id: "11111111-0000-0000-0000-000000000001",
      product_id: "22222222-0000-0000-0000-000000000001",
      warehouse_id: "33333333-0000-0000-0000-000000000001",
      type: "in",
      qty: "50",
      ref_type: "purchase",
      ref_id: null,
      moved_by: "admin-001",
      moved_at: "2026-06-01T10:00:00Z",
      client_uuid: null,
      created_at: "2026-06-01T10:00:00Z",
    },
    {
      id: "11111111-0000-0000-0000-000000000002",
      product_id: "22222222-0000-0000-0000-000000000001",
      warehouse_id: "33333333-0000-0000-0000-000000000001",
      type: "out",
      qty: "10",
      ref_type: "order",
      ref_id: null,
      moved_by: "admin-001",
      moved_at: "2026-06-02T11:00:00Z",
      client_uuid: null,
      created_at: "2026-06-02T11:00:00Z",
    },
  ],
  total: 2,
  limit: 20,
  offset: 0,
};

const mockMovementsEmpty = { items: [], total: 0, limit: 20, offset: 0 };

// ─── API mock ─────────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let movementsResponse: any = mockMovements;

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn((path: string) => {
        if (path.startsWith("/stock/movements"))
          return Promise.resolve(movementsResponse);
        if (path.startsWith("/stock/balance"))
          return Promise.resolve({
            id: "bal-001",
            product_id: "22222222-0000-0000-0000-000000000001",
            warehouse_id: "33333333-0000-0000-0000-000000000001",
            qty_on_hand: "40",
            qty_reserved: "5",
            version: 1,
            updated_at: "2026-06-02T11:00:00Z",
          });
        return Promise.resolve({});
      }),
      post: vi.fn(() =>
        Promise.resolve({
          id: "11111111-0000-0000-0000-000000000099",
          product_id: "22222222-0000-0000-0000-000000000001",
          warehouse_id: "33333333-0000-0000-0000-000000000001",
          type: "in",
          qty: "5",
          ref_type: null,
          ref_id: null,
          moved_by: null,
          moved_at: "2026-06-03T09:00:00Z",
          client_uuid: null,
          created_at: "2026-06-03T09:00:00Z",
        }),
      ),
    },
  };
});

// ─── Auth mock — stock:create ruxsati bilan administrator ─────────────────────

const adminUser: AuthUser = {
  id: "admin-001",
  phone: "+998901234567",
  full_name: "Admin",
  role: "administrator",
  branch_id: null,
  locale: "uz",
  is_active: true,
  biometric_enrolled: false,
  permissions: ["stock:view", "stock:create", "stock:edit", "stock:delete"],
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

import { StockListPage } from "@/features/stock/StockListPage";

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <Notifications />
        <MemoryRouter>
          <StockListPage />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("StockListPage smoke testi", () => {
  beforeEach(() => {
    movementsResponse = mockMovements;
    vi.clearAllMocks();
  });

  it("sahifa sarlavhasi ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      // h3 sarlavhasi aniq "Ombor" matniga ega
      const heading = screen.getByRole("heading", { name: /^ombor$/i });
      expect(heading).toBeInTheDocument();
    });
  });

  it("harakatlar jadvalda ko'rsatiladi (ID va tur bilan)", async () => {
    renderPage();
    await waitFor(() => {
      // "IN" va "OUT" badge'lari ko'rinishi kerak
      expect(screen.getByText("IN")).toBeInTheDocument();
      expect(screen.getByText("OUT")).toBeInTheDocument();
    });
  });

  it("stock:create ruxsati bilan harakat qo'shish tugmasi ko'rinadi", async () => {
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /harakat qo'shish/i }),
      ).toBeInTheDocument();
    });
  });

  it("harakat qo'shish tugmasi bosilganda modal ochiladi", async () => {
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /harakat qo'shish/i }),
      ).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getByRole("button", { name: /harakat qo'shish/i }),
    );

    await waitFor(() => {
      expect(
        screen.getByText(/yangi ombor harakati/i),
      ).toBeInTheDocument();
    });
  });

  it("bo'sh holat ko'rsatiladi", async () => {
    movementsResponse = mockMovementsEmpty;
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByText(/harakat yozuvlari topilmadi/i),
      ).toBeInTheDocument();
    });
  });
});
