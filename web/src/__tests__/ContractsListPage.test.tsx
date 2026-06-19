/**
 * ContractsListPage testlari
 *
 * Tekshiriladi:
 * 1. Sahifa render bo'ladi va jadval sarlavhalari ko'rsatiladi
 * 2. Shartnomalar ro'yxati (mock API) jadvalda ko'rinadi
 * 3. Status badge (active, expiring, expired) to'g'ri ko'rsatiladi
 * 4. Yaratish tugmasi — administrator ko'radi, agent ko'rmaydi
 * 5. <Can contracts:view> — ruxsatsiz rol sahifani ko'rmaydi
 * 6. Bo'sh holat ko'rsatiladi
 * 7. "Tugayotgan" (expiring) filtri bosilganda API status=expiring bilan chaqiriladi
 * 8. O'chirish modal ochiladi (administrator uchun)
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import type { AuthUser } from "@/auth/AuthContext";

// ─── Mock ma'lumotlar ─────────────────────────────────────────────────────────

const mockContracts = {
  items: [
    {
      id: "contract-001",
      store_id: "store-uuid-001",
      number: "SH-2026-001",
      file_url: null,
      signed_at: null,
      valid_from: "2026-01-01",
      valid_to: "2027-01-01",
      contract_type: "trade",
      branch_id: null,
      client_uuid: null,
      status: "active",
      version: 1,
      created_at: "2026-01-01T10:00:00Z",
      updated_at: "2026-01-01T10:00:00Z",
      deleted_at: null,
    },
    {
      id: "contract-002",
      store_id: "store-uuid-002",
      number: "SH-2026-002",
      file_url: null,
      signed_at: null,
      valid_from: "2026-01-01",
      valid_to: "2026-07-01",
      contract_type: "service",
      branch_id: null,
      client_uuid: null,
      status: "expiring",
      version: 1,
      created_at: "2026-01-01T10:00:00Z",
      updated_at: "2026-01-01T10:00:00Z",
      deleted_at: null,
    },
  ],
  total: 2,
  limit: 20,
  offset: 0,
};

const mockContractsEmpty = { items: [], total: 0, limit: 20, offset: 0 };

// ─── API mock ─────────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let contractsResponse: any = mockContracts;

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn((path: string) => {
        if (path.startsWith("/contracts")) return Promise.resolve(contractsResponse);
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
  full_name: "Admin",
  role: "administrator",
  branch_id: null,
  locale: "uz",
  is_active: true,
  biometric_enrolled: false,
  permissions: [
    "contracts:view",
    "contracts:create",
    "contracts:edit",
    "contracts:delete",
  ],
};

const accountantUser: AuthUser = {
  id: "accountant-001",
  phone: "+998901234569",
  full_name: "Buxgalter",
  role: "accountant",
  branch_id: null,
  locale: "uz",
  is_active: true,
  biometric_enrolled: false,
  permissions: ["contracts:view", "contracts:create", "contracts:edit"],
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
  permissions: ["customers:view", "catalog:view"],
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

import { ContractsListPage } from "@/features/contracts/ContractsListPage";

function renderPage(user: AuthUser = adminUser) {
  currentUser = user;
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <Notifications />
        <MemoryRouter>
          <ContractsListPage />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("ContractsListPage", () => {
  beforeEach(() => {
    currentUser = adminUser;
    contractsResponse = mockContracts;
    vi.clearAllMocks();
  });

  it("jadval sarlavhalari render bo'ladi", async () => {
    renderPage(adminUser);

    await waitFor(() => {
      expect(screen.getByText(/raqam/i)).toBeInTheDocument();
      expect(screen.getByText(/boshlanishi/i)).toBeInTheDocument();
      expect(screen.getByText(/tugashi/i)).toBeInTheDocument();
    });
  });

  it("shartnomalar ro'yxati jadvalda ko'rsatiladi", async () => {
    renderPage(adminUser);

    await waitFor(() => {
      expect(screen.getByText("SH-2026-001")).toBeInTheDocument();
      expect(screen.getByText("SH-2026-002")).toBeInTheDocument();
    });
  });

  it("status badge to'g'ri ko'rsatiladi (active, expiring)", async () => {
    renderPage(adminUser);

    await waitFor(() => {
      const amalTexts = screen.getAllByText(/amal qiladi/i);
      expect(amalTexts.length).toBeGreaterThan(0);
      const tugayotganTexts = screen.getAllByText(/tugayotgan/i);
      expect(tugayotganTexts.length).toBeGreaterThan(0);
    });
  });

  it("administrator uchun 'Shartnoma qo'shish' tugmasi ko'rinadi", async () => {
    renderPage(adminUser);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /shartnoma qo'shish/i }),
      ).toBeInTheDocument();
    });
  });

  it("agent uchun 'Shartnoma qo'shish' tugmasi ko'rinmaydi (contracts:create yo'q)", async () => {
    renderPage(agentUser);

    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: /shartnoma qo'shish/i }),
      ).not.toBeInTheDocument();
    });
  });

  it("<Can contracts:view> — agent ruxsatsiz sahifani ko'rmaydi", async () => {
    renderPage(agentUser);

    await waitFor(() => {
      expect(screen.queryByText("SH-2026-001")).not.toBeInTheDocument();
      expect(
        screen.getByText(/bu sahifani ko'rish uchun ruxsat yo'q/i),
      ).toBeInTheDocument();
    });
  });

  it("bo'sh holat: 'Shartnomalar topilmadi' ko'rsatiladi", async () => {
    contractsResponse = mockContractsEmpty;
    renderPage(adminUser);

    await waitFor(() => {
      expect(
        screen.getByText(/shartnomalar topilmadi/i),
      ).toBeInTheDocument();
    });
  });

  it("accountant uchun 'Shartnoma qo'shish' tugmasi ko'rinadi", async () => {
    renderPage(accountantUser);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /shartnoma qo'shish/i }),
      ).toBeInTheDocument();
    });
  });

  it("'Tugayotganlar' filtri bosilganda status=expiring bilan API chaqiriladi", async () => {
    const { apiClient } = await import("@/api/client");
    renderPage(adminUser);

    await waitFor(() => {
      expect(screen.getByText("SH-2026-001")).toBeInTheDocument();
    });

    const expiringBtn = screen.getByRole("button", { name: /tugayotganlar/i });
    fireEvent.click(expiringBtn);

    await waitFor(() => {
      // status=expiring parametri bilan GET chaqirilishi tekshiriladi
      const getCalls = (apiClient.get as ReturnType<typeof vi.fn>).mock.calls;
      const hasExpiringCall = getCalls.some((args: unknown[]) =>
        typeof args[0] === "string" && args[0].includes("status=expiring"),
      );
      expect(hasExpiringCall).toBe(true);
    });
  });

  it("o'chirish tugmasi administrator uchun ko'rsatiladi", async () => {
    renderPage(adminUser);

    await waitFor(() => {
      const deleteBtns = screen.getAllByLabelText(/o'chirish/i);
      expect(deleteBtns.length).toBeGreaterThan(0);
    });
  });

  it("Yaratish modal ochiladi", async () => {
    renderPage(adminUser);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /shartnoma qo'shish/i }),
      ).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getByRole("button", { name: /shartnoma qo'shish/i }),
    );

    await waitFor(() => {
      expect(screen.getByText(/yangi shartnoma/i)).toBeInTheDocument();
      expect(screen.getByText(/shartnoma raqami/i)).toBeInTheDocument();
    });
  });
});
