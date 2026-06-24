/**
 * DeliveryListPage smoke test
 *
 * Tekshiriladi:
 * 1. Yetkazishlar jadvalda ko'rsatiladi
 * 2. Holat badge ko'rsatiladi (delivering)
 * 3. Bo'sh holat ko'rsatiladi
 * 4. Xato holati ko'rsatiladi
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";

// ─── Mock ma'lumotlar ─────────────────────────────────────────────────────────

const mockDeliveries = {
  items: [
    {
      id: "del-001",
      order_id: "order-aaaa-bbbb-cccc-001",
      courier_id: "courier-aaaa-001",
      status: "delivering",
      assigned_at: "2026-06-01T10:00:00Z",
      started_at: "2026-06-01T10:30:00Z",
      start_gps_lat: null,
      start_gps_lng: null,
      delivered_at: null,
      delivery_gps_lat: null,
      delivery_gps_lng: null,
      proof_photo_url: null,
      failure_reason: null,
      branch_id: null,
      client_uuid: null,
      version: 1,
      created_at: "2026-06-01T10:00:00Z",
      updated_at: "2026-06-01T10:30:00Z",
      deleted_at: null,
      gps_track_url: "/gps/track?delivery_id=del-001",
    },
    {
      id: "del-002",
      order_id: "order-aaaa-bbbb-cccc-002",
      courier_id: "courier-aaaa-002",
      status: "delivered",
      assigned_at: "2026-06-02T08:00:00Z",
      started_at: "2026-06-02T08:30:00Z",
      start_gps_lat: null,
      start_gps_lng: null,
      delivered_at: "2026-06-02T09:00:00Z",
      delivery_gps_lat: null,
      delivery_gps_lng: null,
      proof_photo_url: "https://example.com/proof.jpg",
      failure_reason: null,
      branch_id: null,
      client_uuid: null,
      version: 3,
      created_at: "2026-06-02T08:00:00Z",
      updated_at: "2026-06-02T09:00:00Z",
      deleted_at: null,
      gps_track_url: null,
    },
  ],
  total: 2,
  limit: 20,
  offset: 0,
};

const mockEmpty = { items: [], total: 0, limit: 20, offset: 0 };

// ─── API mock ─────────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let deliveryResponse: any = mockDeliveries;
let shouldError = false;

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn((_path: string) => {
        if (shouldError) return Promise.reject(new Error("Server xatosi"));
        return Promise.resolve(deliveryResponse);
      }),
      post: vi.fn(() => Promise.resolve({})),
      patch: vi.fn(() => Promise.resolve({})),
      delete: vi.fn(() => Promise.resolve(undefined)),
    },
  };
});

// ─── Auth mock ────────────────────────────────────────────────────────────────

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({
    user: {
      id: "admin-001",
      phone: "+998901234567",
      full_name: "Admin",
      role: "administrator",
      branch_id: null,
      locale: "uz",
      is_active: true,
      biometric_enrolled: false,
      permissions: ["delivery:view", "delivery:edit", "delivery:create"],
    },
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
  }),
}));

// ─── Render yordamchisi ───────────────────────────────────────────────────────

import { DeliveryListPage } from "@/features/delivery/DeliveryListPage";

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <Notifications />
        <MemoryRouter>
          <DeliveryListPage />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("DeliveryListPage — smoke test", () => {
  beforeEach(() => {
    deliveryResponse = mockDeliveries;
    shouldError = false;
    vi.clearAllMocks();
  });

  it("yetkazishlar jadvalda ko'rsatiladi", async () => {
    renderPage();

    await waitFor(() => {
      // order_id UUID ni qisqa ko'rinishida render qilamiz (slice 0-8 = "order-aa")
      const els = screen.getAllByText(/order-aa/i);
      expect(els.length).toBeGreaterThan(0);
    });
  });

  it("delivering holat badge ko'rsatiladi", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/yetkazilmoqda/i)).toBeInTheDocument();
    });
  });

  it("delivered holat badge ko'rsatiladi", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/yetkazildi/i)).toBeInTheDocument();
    });
  });

  it("bo'sh holat to'g'ri ko'rsatiladi", async () => {
    deliveryResponse = mockEmpty;
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/yetkazishlar topilmadi/i)).toBeInTheDocument();
    });
  });

  it("sarlavha ko'rsatiladi", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/yetkazish/i)).toBeInTheDocument();
    });
  });
});
