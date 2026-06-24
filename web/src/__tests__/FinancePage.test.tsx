/**
 * FinanceLedgerPage — smoke testlari
 *
 * Tekshiriladi:
 * 1. Jadval sarlavhalari render bo'ladi (accountant)
 * 2. Ledger yozuvlari jadvalda ko'rsatiladi
 * 3. Tur badge (debit, credit) to'g'ri rangda ko'rsatiladi
 * 4. "Yozuv qo'shish" tugmasi — accountant ko'radi, store ko'rmaydi
 * 5. <Can finance:view> — ruxsatsiz rol sahifani ko'rmaydi
 * 6. Bo'sh holat ko'rsatiladi
 * 7. "Tasdiqlash" tugmasi accountant ko'radi, store ko'rmaydi
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import type { AuthUser } from "@/auth/AuthContext";

// ─── Mock ma'lumotlar ─────────────────────────────────────────────────────────

const mockLedger = {
  items: [
    {
      id: "entry-001",
      store_id: "store-uuid-001",
      type: "debit",
      amount: "15000.00",
      currency: "UZS",
      ref_type: "order",
      ref_id: null,
      entry_date: "2026-06-01T10:00:00Z",
      created_by: "user-001",
      client_uuid: null,
      created_at: "2026-06-01T10:00:00Z",
    },
    {
      id: "entry-002",
      store_id: "store-uuid-002",
      type: "credit",
      amount: "5000.00",
      currency: "UZS",
      ref_type: null,
      ref_id: null,
      entry_date: "2026-06-02T10:00:00Z",
      created_by: "user-001",
      client_uuid: null,
      created_at: "2026-06-02T10:00:00Z",
    },
  ],
  total: 2,
  limit: 20,
  offset: 0,
};

const mockLedgerEmpty = { items: [], total: 0, limit: 20, offset: 0 };

// ─── API mock ─────────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let ledgerResponse: any = mockLedger;

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn((path: string) => {
        if (path.startsWith("/finance/ledger")) return Promise.resolve(ledgerResponse);
        if (path.startsWith("/finance/balance")) return Promise.resolve({
          id: "bal-001",
          store_id: "store-uuid-001",
          balance: "10000.00",
          currency: "UZS",
          last_recalc_at: "2026-06-01T10:00:00Z",
          version: 1,
        });
        return Promise.resolve({});
      }),
      post: vi.fn(() => Promise.resolve({})),
      patch: vi.fn(() => Promise.resolve({})),
      delete: vi.fn(() => Promise.resolve(undefined)),
    },
  };
});

// ─── Foydalanuvchilar ─────────────────────────────────────────────────────────

const accountantUser: AuthUser = {
  id: "accountant-001",
  phone: "+998901234569",
  full_name: "Buxgalter",
  role: "accountant",
  branch_id: null,
  locale: "uz",
  is_active: true,
  biometric_enrolled: false,
  permissions: ["finance:view", "finance:create", "finance:approve"],
};

const storeUser: AuthUser = {
  id: "store-001",
  phone: "+998901234570",
  full_name: "Do'kon",
  role: "store",
  branch_id: null,
  locale: "uz",
  is_active: true,
  biometric_enrolled: false,
  permissions: ["finance:view"],
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

let currentUser: AuthUser = accountantUser;

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

import { FinanceLedgerPage } from "@/features/finance/FinanceLedgerPage";

function renderPage(user: AuthUser = accountantUser) {
  currentUser = user;
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <Notifications />
        <MemoryRouter>
          <FinanceLedgerPage />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("FinanceLedgerPage", () => {
  beforeEach(() => {
    currentUser = accountantUser;
    ledgerResponse = mockLedger;
    vi.clearAllMocks();
  });

  it("jadval sarlavhalari render bo'ladi (accountant)", async () => {
    renderPage(accountantUser);

    await waitFor(() => {
      // "Turi" va "Havola turi" — ikkalasi ham /turi/i ga mos; getAllByText bilan ambiguity'dan qochamiz
      expect(screen.getAllByText(/turi/i).length).toBeGreaterThan(0);
      expect(screen.getByText(/miqdor/i)).toBeInTheDocument();
      expect(screen.getByText(/sana/i)).toBeInTheDocument();
    });
  });

  it("ledger yozuvlari jadvalda ko'rsatiladi", async () => {
    renderPage(accountantUser);

    await waitFor(() => {
      // store_id lar ko'rinadi
      expect(screen.getByText("store-uuid-001")).toBeInTheDocument();
      expect(screen.getByText("store-uuid-002")).toBeInTheDocument();
    });
  });

  it("tur badge to'g'ri ko'rsatiladi (debit, credit)", async () => {
    renderPage(accountantUser);

    await waitFor(() => {
      const debitBadges = screen.getAllByText(/debet/i);
      expect(debitBadges.length).toBeGreaterThan(0);
      const creditBadges = screen.getAllByText(/kredit/i);
      expect(creditBadges.length).toBeGreaterThan(0);
    });
  });

  it("accountant uchun 'Yozuv qo'shish' tugmasi ko'rinadi", async () => {
    renderPage(accountantUser);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /yozuv qo'shish/i }),
      ).toBeInTheDocument();
    });
  });

  it("store foydalanuvchisi 'Yozuv qo'shish' tugmasini ko'rmaydi (finance:create yo'q)", async () => {
    renderPage(storeUser);

    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: /yozuv qo'shish/i }),
      ).not.toBeInTheDocument();
    });
  });

  it("<Can finance:view> — agent ruxsatsiz sahifani ko'rmaydi", async () => {
    renderPage(agentUser);

    await waitFor(() => {
      expect(screen.queryByText("store-uuid-001")).not.toBeInTheDocument();
      expect(
        screen.getByText(/bu sahifani ko'rish uchun ruxsat yo'q/i),
      ).toBeInTheDocument();
    });
  });

  it("bo'sh holat: 'Yozuvlar topilmadi' ko'rsatiladi", async () => {
    ledgerResponse = mockLedgerEmpty;
    renderPage(accountantUser);

    await waitFor(() => {
      expect(
        screen.getByText(/yozuvlar topilmadi/i),
      ).toBeInTheDocument();
    });
  });

  it("accountant uchun tasdiqlash tugmasi ko'rinadi", async () => {
    renderPage(accountantUser);

    await waitFor(() => {
      const approveBtns = screen.getAllByLabelText(/tasdiqlash/i);
      expect(approveBtns.length).toBeGreaterThan(0);
    });
  });

  it("store foydalanuvchisi tasdiqlash tugmasini ko'rmaydi (finance:approve yo'q)", async () => {
    renderPage(storeUser);

    await waitFor(() => {
      // Ma'lumotlar ko'rinishi kerak (finance:view bor)
      expect(screen.getByText("store-uuid-001")).toBeInTheDocument();
      // Lekin tasdiqlash tugmalari yo'q
      expect(screen.queryAllByLabelText(/tasdiqlash/i)).toHaveLength(0);
    });
  });
});
