/**
 * SuperadminDashboardPage testlari.
 *
 * Tekshiriladi:
 * 1. Dashboard stat kartalar render bo'ladi
 * 2. Stats qiymatlari to'g'ri ko'rsatiladi
 * 3. Xato holati ko'rsatiladi
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import type { AuthUser } from "@/auth/AuthContext";

// ─── Mock ma'lumotlar ─────────────────────────────────────────────────────────

const mockStats = {
  enterprises_total: 42,
  enterprises_active: 38,
  enterprises_suspended: 4,
  users_total: 215,
  enterprises_new_7d: 7,
};

// ─── API mock ─────────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let statsResponse: any = mockStats;
let statsError = false;

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn((path: string) => {
        if (path.startsWith("/superadmin/stats")) {
          if (statsError) return Promise.reject(new Error("Server xatosi"));
          return Promise.resolve(statsResponse);
        }
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

import { SuperadminDashboardPage } from "@/features/superadmin/SuperadminDashboardPage";

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <MemoryRouter>
          <SuperadminDashboardPage />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("SuperadminDashboardPage", () => {
  beforeEach(() => {
    statsResponse = mockStats;
    statsError = false;
    vi.clearAllMocks();
  });

  it("sahifa sarlavhasi render bo'ladi", () => {
    renderPage();
    expect(screen.getByText(/superadmin paneli/i)).toBeInTheDocument();
  });

  it("stat kartalar label'lari ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/jami korxonalar/i)).toBeInTheDocument();
      expect(screen.getByText(/faol korxonalar/i)).toBeInTheDocument();
      expect(screen.getByText(/jami foydalanuvchilar/i)).toBeInTheDocument();
    });
  });

  it("stat qiymatlari to'g'ri ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("42")).toBeInTheDocument();
      expect(screen.getByText("38")).toBeInTheDocument();
      expect(screen.getByText("4")).toBeInTheDocument();
      expect(screen.getByText("215")).toBeInTheDocument();
      expect(screen.getByText("7")).toBeInTheDocument();
    });
  });

  it("xato holati ko'rsatiladi", async () => {
    statsError = true;
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Server xatosi")).toBeInTheDocument();
    });
  });
});
