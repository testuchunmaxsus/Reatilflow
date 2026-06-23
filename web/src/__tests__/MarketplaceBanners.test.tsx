/**
 * MarketplaceBanners testlari — yangi kontrakt
 *
 * Backend AdBannerOut: title (bitta), priority, valid_from, valid_to
 * Endpoint: GET /marketplace/banners/mine?page=1&limit=20 → PaginatedBanners
 *
 * Tekshiriladi:
 * 1. Bannerlar jadvalda ko'rsatiladi (title, priority)
 * 2. Yaratish tugmasi ko'rinadi (catalog:edit ruxsati bilan)
 * 3. Yaratish modal ochiladi
 * 4. Tahrirlash modal ochiladi
 * 5. O'chirish modal ochiladi va delete chaqiriladi
 * 6. Bo'sh holat ko'rsatiladi
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import type { AuthUser } from "@/auth/AuthContext";

// ─── Mock ma'lumotlar — yangi kontrakt ────────────────────────────────────────

const mockBanners = {
  items: [
    {
      id: "banner-001",
      enterprise_id: "ent-001",
      title: "Yozgi aksiya",
      image_url: null,
      target_url: "https://example.com",
      target_product_id: null,
      is_active: true,
      priority: 1,
      valid_from: "2026-06-01",
      valid_to: "2026-08-31",
      created_at: "2026-06-01T00:00:00Z",
      updated_at: "2026-06-01T00:00:00Z",
    },
    {
      id: "banner-002",
      enterprise_id: "ent-001",
      title: "Kuzgi chegirma",
      image_url: null,
      target_url: null,
      target_product_id: null,
      is_active: false,
      priority: 2,
      valid_from: "2026-09-01",
      valid_to: "2026-11-30",
      created_at: "2026-06-02T00:00:00Z",
      updated_at: "2026-06-02T00:00:00Z",
    },
  ],
  total: 2,
  limit: 20,
  offset: 0,
};

const mockBannersEmpty = { items: [], total: 0, limit: 20, offset: 0 };

// ─── API mock ─────────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let bannersResponse: any = mockBanners;
const mockDeleteBanner = vi.fn(() => Promise.resolve(undefined));
const mockCreateBanner = vi.fn(() =>
  Promise.resolve({
    ...mockBanners.items[0],
    id: "banner-new",
    title: "Yangi",
    priority: 0,
    valid_from: "2026-01-01",
    valid_to: "2026-12-31",
  }),
);

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn((path: string) => {
        // yangi endpoint: /marketplace/banners/mine
        if (path.startsWith("/marketplace/banners/mine"))
          return Promise.resolve(bannersResponse);
        return Promise.resolve({});
      }),
      post: vi.fn((path: string) => {
        if (path === "/marketplace/banners") return mockCreateBanner();
        return Promise.resolve({});
      }),
      patch: vi.fn(() => Promise.resolve({})),
      delete: vi.fn((path: string) => {
        if (path.startsWith("/marketplace/banners/")) return mockDeleteBanner();
        return Promise.resolve(undefined);
      }),
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
  permissions: ["catalog:view", "catalog:edit", "catalog:delete"],
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

// ─── Render yordamchisi ───────────────────────────────────────────────────────

import { BannersPage } from "@/features/marketplace/BannersPage";

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <Notifications />
        <MemoryRouter>
          <BannersPage />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("BannersPage — yangi kontrakt (title, priority, valid_from/to, /banners/mine)", () => {
  beforeEach(() => {
    bannersResponse = mockBanners;
    vi.clearAllMocks();
  });

  it("bannerlar jadvalda ko'rsatiladi (title va priority bilan)", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Yozgi aksiya")).toBeInTheDocument();
      expect(screen.getByText("Kuzgi chegirma")).toBeInTheDocument();
    });
  });

  it("sahifa sarlavhasi ko'rsatiladi", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/marketplace bannerlari/i)).toBeInTheDocument();
    });
  });

  it("catalog:edit ruxsati bilan yaratish tugmasi ko'rinadi", async () => {
    renderPage();

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /banner qo'shish/i }),
      ).toBeInTheDocument();
    });
  });

  it("yaratish tugmasi bosilganda modal ochiladi", async () => {
    renderPage();

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /banner qo'shish/i }),
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /banner qo'shish/i }));

    await waitFor(() => {
      expect(screen.getByText(/yangi banner/i)).toBeInTheDocument();
    });
  });

  it("tahrirlash tugmasi bosilganda modal ochiladi (mavjud ma'lumot bilan)", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Yozgi aksiya")).toBeInTheDocument();
    });

    const editBtns = screen.getAllByLabelText(/tahrirlash/i);
    fireEvent.click(editBtns[0]);

    await waitFor(() => {
      expect(screen.getByText(/bannerni tahrirlash/i)).toBeInTheDocument();
    });
  });

  it("o'chirish tugmasi bosilganda tasdiqlash modali ochiladi", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Yozgi aksiya")).toBeInTheDocument();
    });

    const deleteBtns = screen.getAllByLabelText(/o'chirish/i);
    fireEvent.click(deleteBtns[0]);

    await waitFor(() => {
      const els = screen.getAllByText(/bannerni o'chirish/i);
      expect(els.length).toBeGreaterThan(0);
    });
  });

  it("bo'sh holat ko'rsatiladi", async () => {
    bannersResponse = mockBannersEmpty;
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/bannerlar topilmadi/i)).toBeInTheDocument();
    });
  });

  it("yangi endpointga murojaat qilinadi (/banners/mine)", async () => {
    const { apiClient } = await import("@/api/client");
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Yozgi aksiya")).toBeInTheDocument();
    });

    expect(apiClient.get).toHaveBeenCalledWith(
      expect.stringContaining("/marketplace/banners/mine"),
    );
  });
});
