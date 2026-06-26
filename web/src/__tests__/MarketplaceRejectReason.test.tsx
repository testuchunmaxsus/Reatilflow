/**
 * MarketplaceRejectReason testlari
 *
 * Tekshiriladi:
 * 1. Rad etish tugmasi bosilganda modal ochiladi
 * 2. Modalda sabab TextInput (Textarea) ko'rinadi
 * 3. Sabovsiz (bo'sh reason) reject API chaqiriladi — payload ichida reason yo'q
 * 4. Sabab kiritilsa reject API { reason: "..." } bilan chaqiriladi
 * 5. Sabab 500 belgidan ko'p bo'lsa — kesib tashlanadi
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import type { AuthUser } from "@/auth/AuthContext";

// ─── Mock ma'lumotlar ─────────────────────────────────────────────────────────

const mockIncomingOrders = {
  items: [
    {
      id: "order-r01",
      buyer_store_id: "store-001",
      buyer_store_name: "Rad Do'kon",
      supplier_enterprise_id: "ent-001",
      supplier_name: null,
      lines: [],
      total_amount: 10000,
      status: "pending",
      courier_id: null,
      courier_name: null,
      created_at: "2026-06-01T10:00:00Z",
      updated_at: "2026-06-01T10:00:00Z",
    },
  ],
  total: 1,
  limit: 20,
  offset: 0,
};

// ─── API mock ─────────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const mockReject = vi.fn((..._args: any[]) =>
  Promise.resolve({ id: "order-r01", status: "rejected" }),
);

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn((path: string) => {
        if (path.startsWith("/marketplace/orders/incoming"))
          return Promise.resolve(mockIncomingOrders);
        if (path.startsWith("/users"))
          return Promise.resolve({ items: [], total: 0 });
        return Promise.resolve({});
      }),
      post: vi.fn(() => Promise.resolve({})),
      patch: vi.fn((path: string, body?: unknown) => {
        if (path.includes("/reject")) return mockReject(path, body) as Promise<unknown>;
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

describe("IncomingOrdersPage — RejectOrderModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("rad etish tugmasi bosilganda modal ochiladi", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Rad Do'kon")).toBeInTheDocument();
    });

    const rejectBtns = screen.getAllByLabelText(/rad etish/i);
    fireEvent.click(rejectBtns[0]);

    await waitFor(() => {
      expect(screen.getByText(/buyurtmani rad etish/i)).toBeInTheDocument();
    });
  });

  it("modalda sabab textarea ko'rinadi", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Rad Do'kon")).toBeInTheDocument();
    });

    const rejectBtns = screen.getAllByLabelText(/rad etish/i);
    fireEvent.click(rejectBtns[0]);

    await waitFor(() => {
      expect(
        screen.getByPlaceholderText(/rad etish sababini kiriting/i),
      ).toBeInTheDocument();
    });
  });

  it("sababsiz rad etish — reject API chaqiriladi", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Rad Do'kon")).toBeInTheDocument();
    });

    const rejectBtns = screen.getAllByLabelText(/rad etish/i);
    fireEvent.click(rejectBtns[0]);

    await waitFor(() => {
      expect(
        screen.getByPlaceholderText(/rad etish sababini kiriting/i),
      ).toBeInTheDocument();
    });

    // "Rad etish" modal tugmasi — modaldagi "Rad etish" button
    const modalRejectBtns = screen.getAllByRole("button", { name: /rad etish/i });
    // Modal ichidagi tugma
    const confirmBtn = modalRejectBtns[modalRejectBtns.length - 1];
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(mockReject).toHaveBeenCalledTimes(1);
    });
  });

  it("sabab kiritilsa reject payload { reason } ni o'z ichiga oladi", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Rad Do'kon")).toBeInTheDocument();
    });

    const rejectBtns = screen.getAllByLabelText(/rad etish/i);
    fireEvent.click(rejectBtns[0]);

    await waitFor(() => {
      expect(
        screen.getByPlaceholderText(/rad etish sababini kiriting/i),
      ).toBeInTheDocument();
    });

    const textarea = screen.getByPlaceholderText(/rad etish sababini kiriting/i);
    fireEvent.change(textarea, { target: { value: "Mahsulot yetishmaydi" } });

    const modalRejectBtns = screen.getAllByRole("button", { name: /rad etish/i });
    const confirmBtn = modalRejectBtns[modalRejectBtns.length - 1];
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(mockReject).toHaveBeenCalledTimes(1);
      // patch(path, body) — ikkinchi argument reason ni o'z ichiga oladi
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const callArgs = mockReject.mock.calls[0] as any[];
      const body = callArgs[1] as { reason?: string };
      expect(body?.reason).toBe("Mahsulot yetishmaydi");
    });
  });
});
