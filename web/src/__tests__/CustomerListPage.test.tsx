/**
 * CustomerListPage testlari
 *
 * Tekshiriladi:
 * 1. Jadval sarlavhalari render bo'ladi
 * 2. Do'kon ma'lumotlari ko'rsatiladi
 * 3. Admin uchun "Do'kon qo'shish" tugmasi ko'rinadi
 * 4. Agent uchun "Do'kon qo'shish" tugmasi ko'rinmaydi (customers:create yo'q)
 * 5. Kuryer (StoreLimitedOut): PII maydonlar "—" ko'rsatiladi
 * 6. Bo'sh holat: "Do'konlar topilmadi" matni ko'rinadi
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import type { AuthUser } from "@/auth/AuthContext";

// ─── Mock do'konlar ───────────────────────────────────────────────────────────

const mockStoresWithPii = {
  items: [
    {
      id: "store-001",
      name: "Sarvar do'koni",
      inn: "123456789",
      inps: "12345678901234",
      owner_name: "Sarvar Karimov",
      phone: "998901234567",
      address: "Toshkent, Chilonzor 5",
      gps_lat: "41.299496",
      gps_lng: "69.240073",
      segment_id: null,
      agent_id: null,
      branch_id: null,
      credit_limit: "5000000.00",
      user_id: null,
      version: 1,
      created_at: "2026-06-16T10:00:00Z",
      updated_at: "2026-06-16T10:00:00Z",
      deleted_at: null,
    },
  ],
  total: 1,
  limit: 20,
  offset: 0,
};

// Kuryer uchun StoreLimitedOut: PII maydonlar yo'q (null)
// StoreOut tipiga mos: inn, phone, owner_name nullable
const mockStoresLimited = {
  items: [
    {
      id: "store-001",
      name: "Sarvar do'koni",
      inn: null as string | null,
      inps: null as string | null,
      owner_name: null as string | null,
      phone: null as string | null,
      address: "Toshkent, Chilonzor 5",
      gps_lat: "41.299496",
      gps_lng: "69.240073",
      segment_id: null,
      agent_id: null,
      branch_id: null,
      credit_limit: null as string | null,
      user_id: null,
      version: 1,
      created_at: "2026-06-16T10:00:00Z",
      updated_at: "2026-06-16T10:00:00Z",
      deleted_at: null,
    },
  ],
  total: 1,
  limit: 20,
  offset: 0,
};

const mockStoresEmpty = { items: [], total: 0, limit: 20, offset: 0 };

// ─── API mock ─────────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let storesResponse: any = mockStoresWithPii;

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn(() => Promise.resolve(storesResponse)),
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
  full_name: "Admin",
  role: "administrator",
  branch_id: null,
  locale: "uz",
  is_active: true,
  biometric_enrolled: false,
  permissions: [
    "customers:view",
    "customers:create",
    "customers:edit",
    "customers:delete",
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
  permissions: ["customers:view"],
};

const courierUser: AuthUser = {
  id: "courier-001",
  phone: "+998901234569",
  full_name: "Courier",
  role: "courier",
  branch_id: null,
  locale: "uz",
  is_active: true,
  biometric_enrolled: false,
  permissions: ["customers:view"],
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

import { CustomerListPage } from "@/features/customers/CustomerListPage";

function renderCustomerPage(user: AuthUser = adminUser) {
  currentUser = user;
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <Notifications />
        <MemoryRouter>
          <CustomerListPage />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("CustomerListPage", () => {
  beforeEach(() => {
    currentUser = adminUser;
    storesResponse = mockStoresWithPii;
    vi.clearAllMocks();
  });

  it("jadval sarlavhalari render bo'ladi", async () => {
    renderCustomerPage(adminUser);

    await waitFor(() => {
      expect(screen.getByText(/do'kon nomi/i)).toBeInTheDocument();
    });
  });

  it("do'kon ma'lumotlari jadvalda ko'rsatiladi", async () => {
    renderCustomerPage(adminUser);

    await waitFor(() => {
      expect(screen.getByText("Sarvar do'koni")).toBeInTheDocument();
    });
  });

  it("administrator uchun PII ma'lumotlar ko'rsatiladi", async () => {
    renderCustomerPage(adminUser);

    await waitFor(() => {
      expect(screen.getByText("123456789")).toBeInTheDocument();
      expect(screen.getByText("998901234567")).toBeInTheDocument();
    });
  });

  it("admin: 'Do'kon qo'shish' tugmasi ko'rinadi", async () => {
    renderCustomerPage(adminUser);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /do'kon qo'shish/i }),
      ).toBeInTheDocument();
    });
  });

  it("agent: 'Do'kon qo'shish' tugmasi ko'rinmaydi", async () => {
    renderCustomerPage(agentUser);

    await waitFor(() => {
      expect(screen.getByText("Sarvar do'koni")).toBeInTheDocument();
    });

    expect(
      screen.queryByRole("button", { name: /do'kon qo'shish/i }),
    ).not.toBeInTheDocument();
  });

  it("kuryer uchun PII maydonlar '—' ko'rsatiladi (StoreLimitedOut)", async () => {
    storesResponse = mockStoresLimited;
    renderCustomerPage(courierUser);

    await waitFor(() => {
      expect(screen.getByText("Sarvar do'koni")).toBeInTheDocument();
    });

    // PII null bo'lsa "—" ko'rsatiladi
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThan(0);
  });

  it("bo'sh holat: 'Do'konlar topilmadi' ko'rsatiladi", async () => {
    storesResponse = mockStoresEmpty;
    renderCustomerPage(adminUser);

    await waitFor(() => {
      expect(screen.getByText(/do'konlar topilmadi/i)).toBeInTheDocument();
    });
  });
});
