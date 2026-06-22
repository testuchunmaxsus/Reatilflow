/**
 * SuperadminEnterprisesPage testlari — MT5 (C qism).
 *
 * Tekshiriladi:
 * 1. Korxonalar ro'yxati ko'rsatiladi (jadval sarlavhalari + qatorlar)
 * 2. "Korxona qo'shish" tugmasi ko'rinadi
 * 3. Yaratish modali ochiladi va forma maydonlari mavjud
 * 4. Tahrirlash modali ochiladi
 * 5. Suspend tugmasi faol korxona uchun ko'rsatiladi
 * 6. Activate tugmasi to'xtatilgan korxona uchun ko'rsatiladi
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

const mockEnterprises = {
  items: [
    {
      id: "ent-001",
      name: "Alpha Savdo",
      inn: "123456789",
      status: "active",
      enabled_modules: ["catalog", "orders", "customers"],
      version: 1,
      created_at: "2026-06-01T10:00:00Z",
      updated_at: "2026-06-01T10:00:00Z",
    },
    {
      id: "ent-002",
      name: "Beta Distribyutor",
      inn: null,
      status: "suspended",
      enabled_modules: ["catalog"],
      version: 2,
      created_at: "2026-06-05T10:00:00Z",
      updated_at: "2026-06-10T10:00:00Z",
    },
  ],
  total: 2,
  limit: 20,
  offset: 0,
};

const mockEnterprisesEmpty = {
  items: [],
  total: 0,
  limit: 20,
  offset: 0,
};

// ─── API mock ─────────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let enterprisesResponse: any = mockEnterprises;

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn((path: string) => {
        if (path.startsWith("/superadmin/enterprises"))
          return Promise.resolve(enterprisesResponse);
        return Promise.resolve({});
      }),
      post: vi.fn(() =>
        Promise.resolve({
          enterprise: mockEnterprises.items[0],
          admin: {
            id: "admin-new",
            full_name: "Test Admin",
            phone: "+998901234567",
            role: "administrator",
            locale: "uz",
            is_active: true,
            enterprise_id: "ent-001",
            created_at: "2026-06-01T10:00:00Z",
          },
        }),
      ),
      patch: vi.fn(() => Promise.resolve(mockEnterprises.items[0])),
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

import { SuperadminEnterprisesPage } from "@/features/superadmin/SuperadminEnterprisesPage";

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <Notifications />
        <MemoryRouter>
          <SuperadminEnterprisesPage />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("SuperadminEnterprisesPage", () => {
  beforeEach(() => {
    enterprisesResponse = mockEnterprises;
    vi.clearAllMocks();
  });

  it("jadval sarlavhalari render bo'ladi", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/nomi/i)).toBeInTheDocument();
      expect(screen.getByText(/INN/i)).toBeInTheDocument();
      expect(screen.getByText(/holat/i)).toBeInTheDocument();
    });
  });

  it("korxonalar ro'yxati ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Alpha Savdo")).toBeInTheDocument();
      expect(screen.getByText("Beta Distribyutor")).toBeInTheDocument();
    });
  });

  it("active va suspended status badge ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Faol")).toBeInTheDocument();
      expect(screen.getByText("To'xtatilgan")).toBeInTheDocument();
    });
  });

  it("modullar soni ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      // Alpha: 3 ta modul, Beta: 1 ta modul
      expect(screen.getByText("3")).toBeInTheDocument();
      expect(screen.getByText("1")).toBeInTheDocument();
    });
  });

  it("'Korxona qo'shish' tugmasi ko'rinadi", async () => {
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /korxona qo'shish/i }),
      ).toBeInTheDocument();
    });
  });

  it("yaratish modali ochiladi", async () => {
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /korxona qo'shish/i }),
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /korxona qo'shish/i }));

    await waitFor(() => {
      expect(screen.getByText(/yangi korxona/i)).toBeInTheDocument();
      // Forma maydonlari
      expect(screen.getByText(/korxona nomi/i)).toBeInTheDocument();
      expect(screen.getByText(/birinchi administrator/i)).toBeInTheDocument();
    });
  });

  it("tahrirlash modali ochiladi", async () => {
    renderPage();

    await waitFor(() => {
      const editBtns = screen.getAllByLabelText(/tahrirlash/i);
      expect(editBtns.length).toBeGreaterThan(0);
    });

    // Birinchi tahrirlash tugmasini bosish
    fireEvent.click(screen.getAllByLabelText(/tahrirlash/i)[0]);

    await waitFor(() => {
      expect(screen.getByText(/korxonani tahrirlash/i)).toBeInTheDocument();
    });
  });

  it("faol korxona uchun suspend tugmasi ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByLabelText(/to'xtatib qo'yish/i),
      ).toBeInTheDocument();
    });
  });

  it("to'xtatilgan korxona uchun activate tugmasi ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByLabelText(/faollashtirish/i),
      ).toBeInTheDocument();
    });
  });

  it("bo'sh holat ko'rsatiladi", async () => {
    enterprisesResponse = mockEnterprisesEmpty;
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/korxonalar topilmadi/i)).toBeInTheDocument();
    });
  });
});
