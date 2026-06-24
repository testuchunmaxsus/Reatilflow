/**
 * SuperadminUsersPage testlari — cross-tenant foydalanuvchilar.
 *
 * Tekshiriladi:
 * 1. Jadval sarlavhalari render bo'ladi
 * 2. Foydalanuvchilar ro'yxati ko'rsatiladi
 * 3. Telefon maskalangan ko'rsatiladi (PII)
 * 4. Korxona nomi jadvalda ko'rsatiladi
 * 5. Rol badge ko'rsatiladi
 * 6. Korxona filter Select input mavjud
 * 7. Rol filter Select input mavjud
 * 8. Bo'sh holat ko'rsatiladi
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import type { AuthUser } from "@/auth/AuthContext";

// ─── Mock ma'lumotlar ─────────────────────────────────────────────────────────

const mockUsers = {
  items: [
    {
      id: "user-001",
      full_name: "Alisher Nazarov",
      phone: "998901234567",
      role: "administrator",
      is_active: true,
      enterprise_id: "ent-001",
      enterprise_name: "Gamma Kompaniya",
      created_at: "2026-06-01T10:00:00Z",
    },
    {
      id: "user-002",
      full_name: "Barno Tosheva",
      phone: "998901234568",
      role: "agent",
      is_active: false,
      enterprise_id: "ent-002",
      enterprise_name: "Delta Savdo",
      created_at: "2026-06-05T10:00:00Z",
    },
  ],
  total: 2,
  limit: 20,
  offset: 0,
};

const mockUsersEmpty = { items: [], total: 0, limit: 20, offset: 0 };

// Enterprises ro'yxati — foydalanuvchilar jadvalidagi korxona nomlari BILAN FAR
const mockEnterprises = {
  items: [
    {
      id: "ent-filter-001",
      name: "Alpha Filter Savdo",
      inn: null,
      status: "active",
      enabled_modules: [],
      version: 1,
      created_at: "2026-06-01T10:00:00Z",
      updated_at: "2026-06-01T10:00:00Z",
    },
  ],
  total: 1,
  limit: 200,
  offset: 0,
};

// ─── API mock ─────────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let usersResponse: any = mockUsers;

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn((path: string) => {
        if (path.startsWith("/superadmin/users"))
          return Promise.resolve(usersResponse);
        if (path.startsWith("/superadmin/enterprises"))
          return Promise.resolve(mockEnterprises);
        return Promise.resolve({});
      }),
      post: vi.fn(() => Promise.resolve({})),
      patch: vi.fn(() => Promise.resolve({})),
      delete: vi.fn(() => Promise.resolve(undefined)),
    },
  };
});

// ─── Auth mock ────────────────────────────────────────────────────────────────

const superadminUser: AuthUser = {
  id: "superadmin-001",
  phone: "+998900000001",
  full_name: "Superadmin",
  role: "superadmin",
  branch_id: null,
  locale: "uz",
  is_active: true,
  biometric_enrolled: false,
  permissions: [],
};

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({
    user: superadminUser,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
  }),
}));

// ─── Render yordamchisi ───────────────────────────────────────────────────────

import { SuperadminUsersPage } from "@/features/superadmin/SuperadminUsersPage";

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <MemoryRouter>
          <SuperadminUsersPage />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("SuperadminUsersPage", () => {
  beforeEach(() => {
    usersResponse = mockUsers;
    vi.clearAllMocks();
  });

  it("jadval sarlavhalari render bo'ladi", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/ismi/i)).toBeInTheDocument();
      expect(screen.getByText(/telefon/i)).toBeInTheDocument();
      // "Korxona" ustuni sarlavhasi
      const korxonaHeaders = screen.getAllByText(/korxona/i);
      expect(korxonaHeaders.length).toBeGreaterThan(0);
    });
  });

  it("foydalanuvchilar ro'yxati ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Alisher Nazarov")).toBeInTheDocument();
      expect(screen.getByText("Barno Tosheva")).toBeInTheDocument();
    });
  });

  it("korxona nomi jadvalda ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Gamma Kompaniya")).toBeInTheDocument();
      expect(screen.getByText("Delta Savdo")).toBeInTheDocument();
    });
  });

  it("telefon maskalangan ko'rsatiladi (PII)", async () => {
    renderPage();
    await waitFor(() => {
      // 998901234567 (12 ta belgi) → oxirgi 4: 4567, qolgan 8 ta * → ********4567
      const fullPhones = screen.queryAllByText("998901234567");
      expect(fullPhones.length).toBe(0);
      // Maskalangan versiya: "********4567"
      expect(screen.getByText("********4567")).toBeInTheDocument();
    });
  });

  it("rol badge ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Administrator")).toBeInTheDocument();
      expect(screen.getByText("Savdo agenti")).toBeInTheDocument();
    });
  });

  it("faol/nofaol holat ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Faol")).toBeInTheDocument();
      expect(screen.getByText("Bloklangan")).toBeInTheDocument();
    });
  });

  it("korxona filter Select input mavjud", async () => {
    renderPage();
    await waitFor(() => {
      // Select input — aria-label bilan topamiz (Mantine bir nechta element render qilishi mumkin)
      const filterInputs = screen.getAllByLabelText(/korxona bo'yicha filtrlash/i);
      expect(filterInputs.length).toBeGreaterThan(0);
    });
  });

  it("rol filter Select input mavjud", async () => {
    renderPage();
    await waitFor(() => {
      // Rol filter placeholder yoki aria-label
      const roleFilters = screen.getAllByLabelText(/rol bo'yicha filtrlash/i);
      expect(roleFilters.length).toBeGreaterThan(0);
    });
  });

  it("bo'sh holat ko'rsatiladi", async () => {
    usersResponse = mockUsersEmpty;
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/foydalanuvchilar topilmadi/i)).toBeInTheDocument();
    });
  });
});
