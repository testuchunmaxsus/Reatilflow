/**
 * CatalogListPage testlari
 *
 * Tekshiriladi:
 * 1. Jadval sarlavhalari render bo'ladi
 * 2. API ma'lumotlari jadvalda ko'rsatiladi
 * 3. Qidiruv inputi mavjud
 * 4. admin: "Mahsulot qo'shish" tugmasi ko'rinadi (<Can> catalog:create)
 * 5. agent: "Mahsulot qo'shish" tugmasi ko'rinmaydi
 * 6. Faol/nofaol badge to'g'ri ko'rsatiladi
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import type { AuthUser } from "@/auth/AuthContext";
import { CatalogListPage } from "@/features/catalog/CatalogListPage";

// ─── Mock ma'lumotlar ─────────────────────────────────────────────────────────

const mockProducts = {
  items: [
    {
      id: "prod-001",
      name_uz: "Non oq",
      name_ru: "Хлеб белый",
      sku: "BREAD-001",
      barcode: "4600001234567",
      mxik_code: null,
      unit: "dona",
      category_id: "cat-001",
      photo_url: null,
      is_active: true,
      branch_scope: null,
      version: 1,
      created_at: "2026-06-16T10:00:00Z",
      updated_at: "2026-06-16T10:00:00Z",
      deleted_at: null,
    },
    {
      id: "prod-002",
      name_uz: "Limon",
      name_ru: "Лимон",
      sku: "LEMON-001",
      barcode: null,
      mxik_code: "01234567",
      unit: "kg",
      category_id: "cat-001",
      photo_url: null,
      is_active: false,
      branch_scope: null,
      version: 2,
      created_at: "2026-06-16T11:00:00Z",
      updated_at: "2026-06-16T12:00:00Z",
      deleted_at: null,
    },
  ],
  total: 2,
  limit: 20,
  offset: 0,
};

const mockCategories = [
  {
    id: "cat-001",
    name_uz: "Oziq-ovqat",
    name_ru: "Продукты",
    parent_id: null,
    is_active: true,
  },
];

// ─── Enterprise mock ──────────────────────────────────────────────────────────

vi.mock("@/enterprise/EnterpriseContext", () => ({
  useEnterprise: () => ({
    enterprise: { id: "ent-001", name: "Test", inn: null, status: "active", enabled_modules: ["catalog"] },
    isLoading: false,
    hasModule: (key: string) => key === "catalog",
    refreshEnterprise: vi.fn(),
  }),
  EnterpriseProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

// ─── API mock ─────────────────────────────────────────────────────────────────

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn((path: string) => {
        if (path.includes("/catalog/categories"))
          return Promise.resolve(mockCategories);
        if (path.includes("/catalog/price-segments"))
          return Promise.resolve([]);
        if (path.includes("/catalog/products"))
          return Promise.resolve(mockProducts);
        return Promise.resolve({});
      }),
      post: vi.fn(() => Promise.resolve({})),
      patch: vi.fn(() => Promise.resolve({})),
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
  permissions: [
    "catalog:view",
    "catalog:create",
    "catalog:edit",
    "catalog:delete",
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
  permissions: ["catalog:view"],
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

function renderCatalogPage(user: AuthUser = adminUser) {
  currentUser = user;
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <Notifications />
        <MemoryRouter>
          <CatalogListPage />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("CatalogListPage", () => {
  beforeEach(() => {
    currentUser = adminUser;
    vi.clearAllMocks();
  });

  it("jadval sarlavhalari ko'rsatiladi", async () => {
    renderCatalogPage(adminUser);

    await waitFor(() => {
      expect(screen.getByText("Nom")).toBeInTheDocument();
      expect(screen.getByText("SKU")).toBeInTheDocument();
    });
  });

  it("API dan kelgan mahsulotlar jadvalda ko'rsatiladi", async () => {
    renderCatalogPage(adminUser);

    await waitFor(() => {
      expect(screen.getByText("Non oq")).toBeInTheDocument();
      expect(screen.getByText("Limon")).toBeInTheDocument();
      expect(screen.getByText("BREAD-001")).toBeInTheDocument();
    });
  });

  it("qidiruv input maydoni mavjud", async () => {
    renderCatalogPage(adminUser);

    await waitFor(() => {
      expect(
        screen.getByPlaceholderText(/nom, sku yoki barcode/i),
      ).toBeInTheDocument();
    });
  });

  it("administrator uchun 'Mahsulot qo'shish' tugmasi ko'rinadi", async () => {
    renderCatalogPage(adminUser);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /mahsulot qo'shish/i }),
      ).toBeInTheDocument();
    });
  });

  it("agent uchun 'Mahsulot qo'shish' tugmasi ko'rinmaydi", async () => {
    renderCatalogPage(agentUser);

    await waitFor(() => {
      expect(screen.getByText("Non oq")).toBeInTheDocument();
    });

    expect(
      screen.queryByRole("button", { name: /mahsulot qo'shish/i }),
    ).not.toBeInTheDocument();
  });

  it("faol mahsulot 'Faol' badge bilan ko'rinadi", async () => {
    renderCatalogPage(adminUser);

    await waitFor(() => {
      expect(screen.getByText("Faol")).toBeInTheDocument();
    });
  });

  it("nofaol mahsulot 'Nofaol' badge bilan ko'rinadi", async () => {
    renderCatalogPage(adminUser);

    await waitFor(() => {
      expect(screen.getByText("Nofaol")).toBeInTheDocument();
    });
  });
});
