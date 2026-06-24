/**
 * SuperadminEnterprisesPage — delete + search/filter testlari.
 *
 * Tekshiriladi:
 * 1. O'chirish tugmasi ko'rsatiladi
 * 2. O'chirish modali ochiladi
 * 3. DELETE endpoint chaqiriladi
 * 4. Qidiruv maydoni ko'rsatiladi
 * 5. Status filter select ko'rsatiladi
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
      enabled_modules: ["catalog", "orders"],
      version: 1,
      created_at: "2026-06-01T10:00:00Z",
      updated_at: "2026-06-01T10:00:00Z",
    },
  ],
  total: 1,
  limit: 20,
  offset: 0,
};

// ─── API mock — vi.mock hoisting uchun vi.fn() factory ichida ─────────────────

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn((path: string) => {
        if (path.startsWith("/superadmin/enterprises"))
          return Promise.resolve(mockEnterprises);
        if (path.startsWith("/superadmin/stats"))
          return Promise.resolve({
            enterprises_total: 1,
            enterprises_active: 1,
            enterprises_suspended: 0,
            users_total: 5,
            enterprises_new_7d: 1,
          });
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

describe("SuperadminEnterprisesPage — delete + filter", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("o'chirish tugmasi ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Alpha Savdo")).toBeInTheDocument();
    });
    const deleteBtns = screen.getAllByLabelText(/o'chirish/i);
    expect(deleteBtns.length).toBeGreaterThan(0);
  });

  it("o'chirish modali ochiladi", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Alpha Savdo")).toBeInTheDocument();
    });

    const deleteBtns = screen.getAllByLabelText(/o'chirish/i);
    fireEvent.click(deleteBtns[0]);

    await waitFor(() => {
      expect(screen.getByText(/korxonani o'chirish/i)).toBeInTheDocument();
    });
  });

  it("o'chirish modali DELETE endpointni chaqiradi", async () => {
    const { apiClient } = await import("@/api/client");
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Alpha Savdo")).toBeInTheDocument();
    });

    const deleteBtns = screen.getAllByLabelText(/o'chirish/i);
    fireEvent.click(deleteBtns[0]);

    await waitFor(() => {
      expect(screen.getByText(/korxonani o'chirish/i)).toBeInTheDocument();
    });

    // Modal ichidagi tasdiqlash tugmasi — bir nechta bo'lishi mumkin, so'nggi tanlaymiz
    const allDeleteBtns = screen.getAllByRole("button", { name: /o'chirish/i });
    // Oxirgi element — modal tasdiqlash tugmasi
    fireEvent.click(allDeleteBtns[allDeleteBtns.length - 1]);

    await waitFor(() => {
      expect(apiClient.delete).toHaveBeenCalledWith(
        "/superadmin/enterprises/ent-001",
      );
    });
  });

  it("qidiruv maydoni ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      const searchInput = screen.getByPlaceholderText(/nom yoki inn bo'yicha/i);
      expect(searchInput).toBeInTheDocument();
    });
  });

  it("status filter select ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      // Select komponent — "Barcha holatlar" placeholder (input value yoki placeholder)
      const allStatusInput = screen.getByPlaceholderText(/barcha holatlar/i);
      expect(allStatusInput).toBeInTheDocument();
    });
  });
});
