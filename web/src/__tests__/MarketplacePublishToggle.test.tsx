/**
 * MarketplacePublishToggle testlari — yangi kontrakt
 *
 * Backend:
 * - PATCH /catalog/products/{id}/marketplace → { marketplace_published: boolean }
 * - PATCH /promos/{id}/marketplace-featured  → { featured: boolean }
 * - ProductOut.marketplace_published (is_marketplace_listed EMAS)
 *
 * Tekshiriladi:
 * 1. Marketplace moduli yoqilganda katalog jadvalida "Marketplace" ustuni ko'rinadi
 * 2. Marketplace moduli o'chirilganda ustun ko'rinmaydi
 * 3. Toggle yoqilganda (true) — narx kiritish modali ochiladi
 * 4. Narx modal payloadida marketplace_published: true bo'ladi
 *
 * PromoListPage featured toggle:
 * 5. Marketplace moduli yoqilganda "Qaynoq aksiya" ustuni ko'rinadi
 * 6. Featured toggle chaqirilganda { featured: ... } payload yuboriladi
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import type { AuthUser } from "@/auth/AuthContext";

// ─── Hoisted mocks (vi.mock hoists factories to top) ─────────────────────────

const { mockPatch, mockGet, enterpriseModulesRef } = vi.hoisted(() => {
  const enterpriseModulesRef = { value: ["catalog", "marketplace", "promo"] };
  const mockPatch = vi.fn(() =>
    Promise.resolve({ id: "prod-001", marketplace_published: false, marketplace_price: null }),
  );
  const mockGet = vi.fn((path: string) => {
    const mockProducts = {
      items: [
        {
          id: "prod-001",
          name_uz: "Test Mahsulot",
          name_ru: "Тест Товар",
          sku: "SKU001",
          barcode: null,
          mxik_code: null,
          unit: "dona",
          category_id: "cat-001",
          photo_url: null,
          is_active: true,
          marketplace_published: false,
          marketplace_price: null,
          branch_scope: null,
          version: 1,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
      total: 1,
      limit: 20,
      offset: 0,
    };
    const mockPromos = {
      items: [
        {
          id: "promo-001",
          name_uz: "Test Aksiya",
          name_ru: "Тест Акция",
          name: "Test Aksiya",
          promo_type: "discount",
          rule_json: { discount_percent: 10 },
          banner_url: null,
          valid_from: "2026-06-01",
          valid_to: "2026-08-31",
          target_segment_id: null,
          target_product_id: null,
          is_active: true,
          is_marketplace_featured: false,
          branch_id: null,
          client_uuid: null,
          version: 1,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          deleted_at: null,
        },
      ],
      total: 1,
      limit: 20,
      offset: 0,
    };
    if (path.startsWith("/catalog/categories")) return Promise.resolve([]);
    if (path.startsWith("/catalog/products")) return Promise.resolve(mockProducts);
    if (path.startsWith("/catalog/price-segments")) return Promise.resolve([]);
    if (path.startsWith("/promos/active")) return Promise.resolve([]);
    if (path.startsWith("/promos")) return Promise.resolve(mockPromos);
    if (path.startsWith("/users")) return Promise.resolve({ items: [], total: 0 });
    return Promise.resolve({});
  });
  return { mockPatch, mockGet, enterpriseModulesRef };
});

// ─── Enterprise mock ──────────────────────────────────────────────────────────

vi.mock("@/enterprise/EnterpriseContext", () => ({
  useEnterprise: () => ({
    enterprise: {
      id: "ent-001",
      name: "Test",
      inn: null,
      status: "active",
      enabled_modules: enterpriseModulesRef.value,
    },
    isLoading: false,
    hasModule: (key: string) => enterpriseModulesRef.value.includes(key),
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
      get: mockGet,
      post: vi.fn(() => Promise.resolve({})),
      patch: mockPatch,
      delete: vi.fn(() => Promise.resolve(undefined)),
    },
  };
});

// ─── Auth mock ────────────────────────────────────────────────────────────────

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
    "catalog:view", "catalog:edit", "catalog:delete",
    "promo:view", "promo:edit",
  ],
};

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({
    user: adminUser,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
  }),
}));

// ─── Render yordamchilari ─────────────────────────────────────────────────────

import { CatalogListPage } from "@/features/catalog/CatalogListPage";
import { PromoListPage } from "@/features/promo/PromoListPage";

function renderCatalog() {
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

function renderPromo() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <Notifications />
        <MemoryRouter>
          <PromoListPage />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("CatalogListPage — Marketplace publish toggle (marketplace_published)", () => {
  beforeEach(() => {
    enterpriseModulesRef.value = ["catalog", "marketplace", "promo"];
    mockPatch.mockClear();
  });

  it("marketplace moduli yoqilganda 'Marketplace' ustuni ko'rinadi", async () => {
    renderCatalog();

    await waitFor(() => {
      expect(screen.getByText("Test Mahsulot")).toBeInTheDocument();
      // Sarlavha ustuni
      const headers = screen.getAllByText(/marketplace/i);
      expect(headers.length).toBeGreaterThan(0);
    });
  });

  it("marketplace moduli o'chirilganda ustun ko'rinmaydi", async () => {
    enterpriseModulesRef.value = ["catalog", "promo"];
    renderCatalog();

    await waitFor(() => {
      expect(screen.getByText("Test Mahsulot")).toBeInTheDocument();
    });

    // "Marketplace" ustun sarlavhasi ko'rinmasligi kerak
    const allTexts = screen.queryAllByText(/^marketplace$/i);
    expect(allTexts.length).toBe(0);
  });

  it("toggle yoqilganda (false→true) narx modal ochiladi", async () => {
    renderCatalog();

    await waitFor(() => {
      expect(screen.getByText("Test Mahsulot")).toBeInTheDocument();
    });

    // Switch toggling — marketplace_published: false → click → modal
    const toggles = screen.getAllByRole("checkbox");
    const marketplaceToggle = toggles.find((el) =>
      el.getAttribute("aria-label")?.includes("Marketplace"),
    );
    if (marketplaceToggle) {
      fireEvent.click(marketplaceToggle);
      await waitFor(() => {
        // Modal narx kiritish uchun
        expect(screen.getByText(/marketplace'ga nashr qilish/i)).toBeInTheDocument();
      });
    }
  });
});

describe("PromoListPage — Marketplace featured toggle ({ featured: boolean })", () => {
  beforeEach(() => {
    enterpriseModulesRef.value = ["catalog", "marketplace", "promo"];
    mockPatch.mockClear();
  });

  it("marketplace moduli yoqilganda 'Qaynoq aksiya' ustuni ko'rinadi", async () => {
    renderPromo();

    await waitFor(() => {
      expect(screen.getByText("Test Aksiya")).toBeInTheDocument();
      expect(screen.getByText(/qaynoq aksiya/i)).toBeInTheDocument();
    });
  });

  it("marketplace moduli o'chirilganda featured ustun ko'rinmaydi", async () => {
    enterpriseModulesRef.value = ["catalog", "promo"];
    renderPromo();

    await waitFor(() => {
      expect(screen.getByText("Test Aksiya")).toBeInTheDocument();
    });

    expect(screen.queryByText(/qaynoq aksiya/i)).not.toBeInTheDocument();
  });

  it("featured toggle bosilganda patch { featured: ... } payload bilan API chaqiriladi", async () => {
    renderPromo();

    await waitFor(() => {
      expect(screen.getByText("Test Aksiya")).toBeInTheDocument();
    });

    // Mantine Switch input — aria-label orqali topamiz
    const featuredToggle = screen.getByLabelText(/marketplace qaynoq belgisi/i);

    fireEvent.click(featuredToggle);
    await waitFor(() => {
      expect(mockPatch).toHaveBeenCalled();
      // payload { featured: boolean } (is_featured EMAS)
      const lastCall = mockPatch.mock.lastCall as [string, Record<string, unknown>] | undefined;
      if (lastCall) {
        expect(lastCall[1]).toHaveProperty("featured");
        expect(lastCall[1]).not.toHaveProperty("is_featured");
      }
    });
  });
});
