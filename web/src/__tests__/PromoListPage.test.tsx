/**
 * PromoListPage testlari
 *
 * Tekshiriladi:
 * 1. Sahifa render bo'ladi va jadval sarlavhalari ko'rsatiladi
 * 2. Aksiyalar ro'yxati (mock API) jadvalda ko'rinadi
 * 3. is_active badge to'g'ri ko'rsatiladi
 * 4. Yaratish tugmasi — faqat administrator ko'radi (promo:create)
 * 5. <Can promo:view> — ruxsatsiz rol sahifani ko'rmaydi
 * 6. Bo'sh holat ko'rsatiladi
 * 7. rule_json: xom UUID emas, discount_percent/amount ko'rsatiladi
 * 8. target_segment va target_product — mavjud ro'yxatdan Select (xom UUID emas)
 * 9. Yaratish modalida discount_mode va discount_value maydonlari mavjud
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import type { AuthUser } from "@/auth/AuthContext";

// ─── Mock ma'lumotlar ─────────────────────────────────────────────────────────

const mockPromos = {
  items: [
    {
      id: "promo-001",
      name_uz: "Yoz chegirmasi",
      name_ru: "Летняя скидка",
      name: "Yoz chegirmasi",
      promo_type: "discount",
      rule_json: { discount_percent: 10 },
      banner_url: null,
      valid_from: "2026-06-01",
      valid_to: "2026-08-31",
      target_segment_id: null,
      target_product_id: null,
      is_active: true,
      branch_id: null,
      client_uuid: null,
      version: 1,
      created_at: "2026-06-01T10:00:00Z",
      updated_at: "2026-06-01T10:00:00Z",
      deleted_at: null,
    },
    {
      id: "promo-002",
      name_uz: "Kuzgi bonus",
      name_ru: "Осенний бонус",
      name: "Kuzgi bonus",
      promo_type: "bonus",
      rule_json: { discount_amount: 5000, min_qty: 3 },
      banner_url: null,
      valid_from: "2026-09-01",
      valid_to: "2026-11-30",
      target_segment_id: null,
      target_product_id: null,
      is_active: false,
      branch_id: null,
      client_uuid: null,
      version: 1,
      created_at: "2026-06-01T10:00:00Z",
      updated_at: "2026-06-01T10:00:00Z",
      deleted_at: null,
    },
  ],
  total: 2,
  limit: 20,
  offset: 0,
};

const mockSegments = [
  { id: "segment-001", name: "Premium" },
  { id: "segment-002", name: "Standard" },
];

const mockProducts = {
  items: [
    { id: "product-001", name_uz: "Mahsulot 1", name_ru: "Продукт 1" },
    { id: "product-002", name_uz: "Mahsulot 2", name_ru: "Продукт 2" },
  ],
};

const mockPromosEmpty = { items: [], total: 0, limit: 20, offset: 0 };

// ─── API mock ─────────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let promosResponse: any = mockPromos;

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn((path: string) => {
        if (path.startsWith("/promos/active"))
          return Promise.resolve([]);
        if (path.startsWith("/promos"))
          return Promise.resolve(promosResponse);
        if (path.startsWith("/catalog/price-segments"))
          return Promise.resolve(mockSegments);
        if (path.startsWith("/catalog/products"))
          return Promise.resolve(mockProducts);
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
    "promo:view",
    "promo:create",
    "promo:edit",
    "promo:delete",
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
  // Accountant faqat view ga ega (backend RBAC: promo:create faqat administrator)
  permissions: ["promo:view"],
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
  // Agent promo:view ga ega (backend barcha rol ko'ra oladi)
  permissions: ["promo:view", "customers:view"],
};

const noPermUser: AuthUser = {
  id: "noperm-001",
  phone: "+998901234560",
  full_name: "NoPerms",
  role: "courier",
  branch_id: null,
  locale: "uz",
  is_active: true,
  biometric_enrolled: false,
  permissions: [],
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

import { PromoListPage } from "@/features/promo/PromoListPage";

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
          <PromoListPage />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("PromoListPage", () => {
  beforeEach(() => {
    currentUser = adminUser;
    promosResponse = mockPromos;
    vi.clearAllMocks();
  });

  it("jadval sarlavhalari render bo'ladi", async () => {
    renderPage(adminUser);

    await waitFor(() => {
      // "Nomi" sarlavhasi — jadval th da
      const nomiTexts = screen.getAllByText(/^nomi$/i);
      expect(nomiTexts.length).toBeGreaterThan(0);
      // "Chegirma" sarlavhasi
      const chegirmaTexts = screen.getAllByText(/^chegirma$/i);
      expect(chegirmaTexts.length).toBeGreaterThan(0);
      // "Boshlanishi" sarlavhasi
      const boshlanishiTexts = screen.getAllByText(/^boshlanishi$/i);
      expect(boshlanishiTexts.length).toBeGreaterThan(0);
    });
  });

  it("aksiyalar ro'yxati jadvalda ko'rsatiladi", async () => {
    renderPage(adminUser);

    await waitFor(() => {
      expect(screen.getByText("Yoz chegirmasi")).toBeInTheDocument();
      expect(screen.getByText("Kuzgi bonus")).toBeInTheDocument();
    });
  });

  it("is_active badge to'g'ri ko'rsatiladi", async () => {
    renderPage(adminUser);

    await waitFor(() => {
      expect(screen.getByText("Faol")).toBeInTheDocument();
      expect(screen.getByText("Nofaol")).toBeInTheDocument();
    });
  });

  it("rule_json dan chegirma qiymati ko'rsatiladi (xom UUID emas)", async () => {
    renderPage(adminUser);

    await waitFor(() => {
      // discount_percent: 10 → "10%" ko'rsatilishi kerak
      expect(screen.getByText(/10%/)).toBeInTheDocument();
      // discount_amount: 5000 → "5 000 UZS" yoki "5000 UZS"
      expect(screen.getByText(/5[,\s.]?000.*UZS/)).toBeInTheDocument();
    });
  });

  it("min_qty ko'rsatiladi", async () => {
    renderPage(adminUser);

    await waitFor(() => {
      // min_qty: 3 → "(min 3)" ko'rsatilishi kerak
      expect(screen.getByText(/min 3/)).toBeInTheDocument();
    });
  });

  it("administrator uchun 'Aksiya qo'shish' tugmasi ko'rinadi", async () => {
    renderPage(adminUser);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /aksiya qo'shish/i }),
      ).toBeInTheDocument();
    });
  });

  it("accountant uchun 'Aksiya qo'shish' tugmasi ko'rinmaydi (promo:create yo'q)", async () => {
    renderPage(accountantUser);

    await waitFor(() => {
      expect(screen.getByText("Yoz chegirmasi")).toBeInTheDocument();
    });

    expect(
      screen.queryByRole("button", { name: /aksiya qo'shish/i }),
    ).not.toBeInTheDocument();
  });

  it("<Can promo:view> — ruxsatsiz rol sahifani ko'rmaydi", async () => {
    renderPage(noPermUser);

    await waitFor(() => {
      expect(
        screen.queryByText("Yoz chegirmasi"),
      ).not.toBeInTheDocument();
      expect(
        screen.getByText(/bu sahifani ko'rish uchun ruxsat yo'q/i),
      ).toBeInTheDocument();
    });
  });

  it("bo'sh holat: 'Aksiyalar topilmadi' ko'rsatiladi", async () => {
    promosResponse = mockPromosEmpty;
    renderPage(adminUser);

    await waitFor(() => {
      expect(screen.getByText(/aksiyalar topilmadi/i)).toBeInTheDocument();
    });
  });

  it("Yaratish modal ochiladi va discount_mode/discount_value maydonlari mavjud", async () => {
    renderPage(adminUser);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /aksiya qo'shish/i }),
      ).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getByRole("button", { name: /aksiya qo'shish/i }),
    );

    await waitFor(() => {
      expect(screen.getByText(/yangi aksiya/i)).toBeInTheDocument();
      // Chegirma turi dropdown mavjud (xom UUID emas, Select komponent)
      expect(screen.getByText(/chegirma turi/i)).toBeInTheDocument();
      // discount_percent / discount_amount label mavjud
      expect(
        screen.getByText(/chegirma foizi|chegirma miqdori/i),
      ).toBeInTheDocument();
    });
  });

  it("Yaratish modal da narx segmenti Select mavjud (xom UUID emas)", async () => {
    renderPage(adminUser);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /aksiya qo'shish/i }),
      ).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getByRole("button", { name: /aksiya qo'shish/i }),
    );

    await waitFor(() => {
      // "Narx segmenti" label mavjud — TextInput emas, Select
      expect(screen.getByText(/narx segmenti/i)).toBeInTheDocument();
      // "Mahsulot" label mavjud — TextInput emas, Select
      expect(screen.getByText(/^mahsulot$/i)).toBeInTheDocument();
    });
  });

  it("agent promo:view bor bo'lsa aksiyalarni ko'ra oladi", async () => {
    renderPage(agentUser);

    await waitFor(() => {
      expect(screen.getByText("Yoz chegirmasi")).toBeInTheDocument();
      expect(screen.getByText("Kuzgi bonus")).toBeInTheDocument();
    });
  });
});
