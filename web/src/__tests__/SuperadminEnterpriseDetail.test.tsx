/**
 * SuperadminEnterpriseDetailPage testlari.
 *
 * Tekshiriladi:
 * 1. Korxona ma'lumoti render bo'ladi
 * 2. Adminlar ro'yxati ko'rsatiladi
 * 3. Parol reset tugmasi ko'rsatiladi
 * 4. Parol reset modali ochiladi va parol generatsiya qilinadi
 * 5. CopyButton mavjud generatsiya qilingan parol yonida
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import type { AuthUser } from "@/auth/AuthContext";

// ─── Mock ma'lumotlar ─────────────────────────────────────────────────────────

const mockDetail = {
  id: "ent-001",
  name: "Alpha Savdo",
  inn: "123456789",
  status: "active",
  enabled_modules: ["catalog", "orders", "customers"],
  version: 1,
  created_at: "2026-06-01T10:00:00Z",
  updated_at: "2026-06-10T10:00:00Z",
  user_count: 15,
  admins: [
    {
      id: "admin-001",
      full_name: "Jasur Admin",
      phone: "+998901234567",
      role: "administrator",
      is_active: true,
      created_at: "2026-06-01T10:00:00Z",
    },
  ],
};

const mockResetResponse = {
  user_id: "admin-001",
  new_password: "SecurePass123",
};

// ─── API mock — vi.mock hoisting uchun vi.fn() factory ichida ─────────────────

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn((path: string) => {
        if (path.startsWith("/superadmin/enterprises/ent-001"))
          return Promise.resolve(mockDetail);
        return Promise.resolve({});
      }),
      post: vi.fn((path: string) => {
        if (path.includes("reset-admin-password"))
          return Promise.resolve(mockResetResponse);
        return Promise.resolve({});
      }),
      patch: vi.fn(() => Promise.resolve(mockDetail)),
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

import { SuperadminEnterpriseDetailPage } from "@/features/superadmin/SuperadminEnterpriseDetailPage";

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <Notifications />
        <MemoryRouter initialEntries={["/superadmin/enterprises/ent-001"]}>
          <Routes>
            <Route
              path="/superadmin/enterprises/:id"
              element={<SuperadminEnterpriseDetailPage />}
            />
          </Routes>
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("SuperadminEnterpriseDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("korxona nomi ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Alpha Savdo")).toBeInTheDocument();
    });
  });

  it("korxona ma'lumotlari ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("123456789")).toBeInTheDocument();
      // user_count
      expect(screen.getByText("15")).toBeInTheDocument();
    });
  });

  it("adminlar ro'yxati ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Jasur Admin")).toBeInTheDocument();
    });
  });

  it("parol reset tugmasi ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      const resetBtns = screen.getAllByLabelText(/parolni reset qilish/i);
      expect(resetBtns.length).toBeGreaterThan(0);
    });
  });

  it("parol reset modali ochiladi", async () => {
    renderPage();
    await waitFor(() => {
      const resetBtns = screen.getAllByLabelText(/parolni reset qilish/i);
      expect(resetBtns.length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getAllByLabelText(/parolni reset qilish/i)[0]);

    await waitFor(() => {
      // Modal titlini emas, "yangi parol yaratish" tugmasini tekshiramiz
      expect(screen.getByRole("button", { name: /yangi parol yaratish/i })).toBeInTheDocument();
    });
  });

  it("parol generatsiya qilinadi va ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      const resetBtns = screen.getAllByLabelText(/parolni reset qilish/i);
      expect(resetBtns.length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getAllByLabelText(/parolni reset qilish/i)[0]);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /yangi parol yaratish/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /yangi parol yaratish/i }));

    await waitFor(() => {
      expect(screen.getByText("SecurePass123")).toBeInTheDocument();
      // Bir marta ko'rinish haqida ogohlantirish
      expect(screen.getByText(/faqat bir marta ko'rsatiladi/i)).toBeInTheDocument();
    });
  });

  it("nusxa olish tugmasi generatsiya qilingan parol yonida mavjud", async () => {
    renderPage();
    await waitFor(() => {
      const resetBtns = screen.getAllByLabelText(/parolni reset qilish/i);
      expect(resetBtns.length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getAllByLabelText(/parolni reset qilish/i)[0]);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /yangi parol yaratish/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /yangi parol yaratish/i }));

    await waitFor(() => {
      expect(screen.getByText("SecurePass123")).toBeInTheDocument();
      // Nusxa olish — tooltip label yoki ActionIcon aria-label
      const copyEl = screen.getByLabelText(/nusxa olish/i);
      expect(copyEl).toBeInTheDocument();
    });
  });
});
