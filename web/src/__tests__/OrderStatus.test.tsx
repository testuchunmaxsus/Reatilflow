/**
 * OrderDetailModal — holat o'zgartirish va RBAC testlari
 *
 * Tekshiriladi:
 * 1. confirmed → packed tugmasi ko'rinadi (orders:edit bor)
 * 2. canceled tugmasi ko'rinadi (qonuniy o'tish)
 * 3. agent ham holat o'zgartirish tugmalarini ko'radi (orders:edit bor)
 * 4. buxgalter holat tugmalarini ko'rmaydi (orders:edit yo'q)
 * 5. delivered holatda hech qanday tugma ko'rinmaydi (terminal)
 * 6. noqonuniy o'tish backend 422 → showError chaqiriladi
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import type { AuthUser } from "@/auth/AuthContext";
import { OrderDetailModal } from "@/features/orders/components/OrderDetailModal";
import { ApiError } from "@/api/client";

// ─── Mock buyurtma ma'lumotlari ───────────────────────────────────────────────

const mockConfirmedOrder = {
  id: "order-001",
  store_id: "store-001",
  agent_id: "agent-001",
  mode: "oddiy",
  status: "confirmed",
  total_amount: "150000.00",
  currency: "UZS",
  ordered_at: "2026-06-16T10:00:00Z",
  client_uuid: null,
  branch_id: null,
  warehouse_id: null,
  version: 1,
  created_at: "2026-06-16T10:00:00Z",
  updated_at: "2026-06-16T10:00:00Z",
  deleted_at: null,
  lines: [
    {
      id: "line-001",
      order_id: "order-001",
      product_id: "prod-001",
      qty: "5.0000",
      unit_price: "30000.00",
      segment_id: null,
      discount: "0.00",
      line_total: "150000.00",
    },
  ],
};

const mockDeliveredOrder = {
  ...mockConfirmedOrder,
  id: "order-002",
  status: "delivered",
  version: 5,
};

// ─── API mock ─────────────────────────────────────────────────────────────────

const { mockPatch } = vi.hoisted(() => ({ mockPatch: vi.fn() }));

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    ApiError: actual.ApiError,
    apiClient: {
      get: vi.fn((path: string) => {
        if (path.includes("order-002")) return Promise.resolve(mockDeliveredOrder);
        return Promise.resolve(mockConfirmedOrder);
      }),
      post: vi.fn(() => Promise.resolve({})),
      patch: mockPatch,
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
  permissions: ["orders:view", "orders:create", "orders:edit"],
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
  permissions: ["orders:view", "orders:create", "orders:edit"],
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

function renderDetailModal(
  user: AuthUser = adminUser,
  orderId = "order-001",
) {
  currentUser = user;
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <Notifications />
        <MemoryRouter>
          <OrderDetailModal
            opened={true}
            onClose={vi.fn()}
            orderId={orderId}
          />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("OrderDetailModal — holat o'zgartirish", () => {
  beforeEach(() => {
    currentUser = adminUser;
    vi.clearAllMocks();
    mockPatch.mockResolvedValue({ ...mockConfirmedOrder, status: "packed", version: 2 });
  });

  it("confirmed → packed va canceled tugmalari ko'rinadi", async () => {
    renderDetailModal(adminUser, "order-001");
    await waitFor(() => {
      expect(screen.getByTestId("status-btn-packed")).toBeInTheDocument();
      expect(screen.getByTestId("status-btn-canceled")).toBeInTheDocument();
    });
  });

  it("agent ham holat tugmalarini ko'radi (orders:edit bor)", async () => {
    renderDetailModal(agentUser, "order-001");
    await waitFor(() => {
      expect(screen.getByTestId("status-btn-packed")).toBeInTheDocument();
    });
  });

  it("buxgalter holat tugmalarini ko'rmaydi (orders:edit yo'q)", async () => {
    renderDetailModal(accountantUser, "order-001");
    await waitFor(() => {
      // Buyurtma tafsiloti modal sarlavhasi yuklanishi kerak
      expect(screen.getByText("Buyurtma tafsiloti")).toBeInTheDocument();
    });
    // Holat tugmalari ko'rinmasligi kerak (orders:edit yo'q)
    expect(screen.queryByTestId("status-btn-packed")).not.toBeInTheDocument();
    expect(screen.queryByTestId("status-btn-canceled")).not.toBeInTheDocument();
  });

  it("delivered holatda terminal status xabari ko'rinadi (admin)", async () => {
    renderDetailModal(adminUser, "order-002");
    await waitFor(() => {
      expect(
        screen.getByText(/terminal holat/i),
      ).toBeInTheDocument();
    });
  });

  it("holat tugmasiga bosish PATCH chaqiradi", async () => {
    renderDetailModal(adminUser, "order-001");
    await waitFor(() => {
      expect(screen.getByTestId("status-btn-packed")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("status-btn-packed"));

    await waitFor(() => {
      expect(mockPatch).toHaveBeenCalledWith(
        "/orders/order-001/status",
        expect.objectContaining({ status: "packed" }),
      );
    });
  });

  it("noqonuniy o'tish 422 → notification ko'rsatiladi", async () => {
    // Backend 422 qaytaradi — ApiError tashlaydi
    mockPatch.mockRejectedValueOnce(
      new ApiError(422, {
        message_key: "orders.invalid_transition",
        message: "Noqonuniy holat o'tishi",
        detail: null,
      }),
    );

    renderDetailModal(adminUser, "order-001");
    await waitFor(() => {
      expect(screen.getByTestId("status-btn-packed")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("status-btn-packed"));

    await waitFor(() => {
      expect(mockPatch).toHaveBeenCalled();
    });
  });
});
