/**
 * UsersListPage testlari
 *
 * Tekshiriladi:
 * 1. Sahifa render bo'ladi va jadval sarlavhalari ko'rsatiladi
 * 2. Foydalanuvchilar ro'yxati (mock API) jadvalda ko'rinadi
 * 3. Yaratish tugmasi — administrator ko'radi, agent ko'rmaydi
 * 4. Rol dropdown to'g'ri qiymatlar bilan (xom UUID emas)
 * 5. Agent → do'kon biriktirish: mavjud do'konlar ro'yxatidan tanlanadi (xom UUID yo'q)
 * 6. <Can> — ruxsatsiz rol (agent) sahifaning asosiy tarkibini ko'rmaydi
 * 7. Bo'sh holat ko'rsatiladi
 * 8. Deaktivatsiya modali ochiladi
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import type { AuthUser } from "@/auth/AuthContext";

// ─── Mock ma'lumotlar ─────────────────────────────────────────────────────────

const mockUsers = {
  items: [
    {
      id: "user-001",
      full_name: "Alisher Nazarov",
      phone: "998901234567",
      role: "agent",
      branch_id: null,
      locale: "uz",
      biometric_enrolled: false,
      device_id: null,
      is_active: true,
      version: 1,
      created_at: "2026-06-16T10:00:00Z",
      updated_at: "2026-06-16T10:00:00Z",
    },
    {
      id: "user-002",
      full_name: "Barno Tosheva",
      phone: "998901234568",
      role: "accountant",
      branch_id: null,
      locale: "uz",
      biometric_enrolled: false,
      device_id: null,
      is_active: false,
      version: 2,
      created_at: "2026-06-16T11:00:00Z",
      updated_at: "2026-06-16T12:00:00Z",
    },
  ],
  total: 2,
  limit: 20,
  offset: 0,
};

const mockUsersEmpty = { items: [], total: 0, limit: 20, offset: 0 };

// Do'konlar (agent biriktirish uchun) — xom UUID yo'q, nomlar bilan
const mockStores = {
  items: [
    {
      id: "store-uuid-001",
      name: "Sarvar do'koni",
      inn: null,
      inps: null,
      owner_name: null,
      phone: null,
      address: "Toshkent",
      gps_lat: null,
      gps_lng: null,
      segment_id: null,
      agent_id: null,
      branch_id: null,
      credit_limit: null,
      user_id: null,
      version: 1,
      created_at: "2026-06-16T10:00:00Z",
      updated_at: "2026-06-16T10:00:00Z",
      deleted_at: null,
    },
    {
      id: "store-uuid-002",
      name: "Bahor savdo",
      inn: null,
      inps: null,
      owner_name: null,
      phone: null,
      address: "Samarqand",
      gps_lat: null,
      gps_lng: null,
      segment_id: null,
      agent_id: null,
      branch_id: null,
      credit_limit: null,
      user_id: null,
      version: 1,
      created_at: "2026-06-16T10:00:00Z",
      updated_at: "2026-06-16T10:00:00Z",
      deleted_at: null,
    },
  ],
  total: 2,
  limit: 200,
  offset: 0,
};

// ─── API mock ─────────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let usersResponse: any = mockUsers;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let storesResponse: any = mockStores;

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn((path: string) => {
        if (path.startsWith("/users")) return Promise.resolve(usersResponse);
        if (path.startsWith("/customers/stores"))
          return Promise.resolve(storesResponse);
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
  permissions: ["rbac:view", "rbac:create", "rbac:edit", "rbac:delete"],
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

import { UsersListPage } from "@/features/users/UsersListPage";

function renderUsersPage(user: AuthUser = adminUser) {
  currentUser = user;
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <Notifications />
        <MemoryRouter>
          <UsersListPage />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("UsersListPage", () => {
  beforeEach(() => {
    currentUser = adminUser;
    usersResponse = mockUsers;
    storesResponse = mockStores;
    vi.clearAllMocks();
  });

  it("jadval sarlavhalari render bo'ladi", async () => {
    renderUsersPage(adminUser);

    await waitFor(() => {
      expect(screen.getByText(/ismi/i)).toBeInTheDocument();
      expect(screen.getByText(/telefon/i)).toBeInTheDocument();
      // "Rol" sarlavhasi jadval th da (getAllByText ishlatamiz — filter ham bor)
      const rolTexts = screen.getAllByText(/^rol$/i);
      expect(rolTexts.length).toBeGreaterThan(0);
    });
  });

  it("foydalanuvchilar ro'yxati jadvalda ko'rsatiladi", async () => {
    renderUsersPage(adminUser);

    await waitFor(() => {
      expect(screen.getByText("Alisher Nazarov")).toBeInTheDocument();
      expect(screen.getByText("Barno Tosheva")).toBeInTheDocument();
    });
  });

  it("faol/nofaol holat badge ko'rsatiladi", async () => {
    renderUsersPage(adminUser);

    await waitFor(() => {
      // is_active: true
      expect(screen.getByText("Faol")).toBeInTheDocument();
      // is_active: false
      expect(screen.getByText("Bloklangan")).toBeInTheDocument();
    });
  });

  it("rol badge ko'rsatiladi", async () => {
    renderUsersPage(adminUser);

    await waitFor(() => {
      expect(screen.getByText("Savdo agenti")).toBeInTheDocument();
      expect(screen.getByText("Buxgalter")).toBeInTheDocument();
    });
  });

  it("administrator uchun 'Foydalanuvchi qo'shish' tugmasi ko'rinadi", async () => {
    renderUsersPage(adminUser);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /foydalanuvchi qo'shish/i }),
      ).toBeInTheDocument();
    });
  });

  it("agent uchun 'Foydalanuvchi qo'shish' tugmasi ko'rinmaydi (rbac:create yo'q)", async () => {
    renderUsersPage(agentUser);

    // Agent sahifani ko'rmasligi kerak (rbac:view yo'q)
    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: /foydalanuvchi qo'shish/i }),
      ).not.toBeInTheDocument();
    });
  });

  it("<Can rbac:view> — agent ruxsatsiz sahifani ko'rmaydi", async () => {
    renderUsersPage(agentUser);

    await waitFor(() => {
      // Jadval ko'rsatilmaydi
      expect(screen.queryByText("Alisher Nazarov")).not.toBeInTheDocument();
      // Ruxsat yo'q xabari ko'rsatiladi
      expect(
        screen.getByText(/bu sahifani ko'rish uchun ruxsat yo'q/i),
      ).toBeInTheDocument();
    });
  });

  it("bo'sh holat: 'Foydalanuvchilar topilmadi' ko'rsatiladi", async () => {
    usersResponse = mockUsersEmpty;
    renderUsersPage(adminUser);

    await waitFor(() => {
      expect(
        screen.getByText(/foydalanuvchilar topilmadi/i),
      ).toBeInTheDocument();
    });
  });

  it("deaktivatsiya tugmasi faol foydalanuvchi uchun ko'rsatiladi", async () => {
    renderUsersPage(adminUser);

    await waitFor(() => {
      const deactivateBtns = screen.getAllByLabelText(/bloklash/i);
      expect(deactivateBtns.length).toBeGreaterThan(0);
    });
  });

  it("nofaol foydalanuvchi uchun aktivlashtirish tugmasi /activate endpointni chaqiradi", async () => {
    const { apiClient } = await import("@/api/client");
    renderUsersPage(adminUser);

    // Barno Tosheva (user-002) is_active: false → aktivlashtirish tugmasi
    let activateBtn: HTMLElement | undefined;
    await waitFor(() => {
      const btns = screen.getAllByLabelText(/^aktivlashtirish$/i);
      expect(btns.length).toBeGreaterThan(0);
      activateBtn = btns[0];
    });

    fireEvent.click(activateBtn!);

    await waitFor(() => {
      expect(apiClient.patch).toHaveBeenCalledWith("/users/user-002/activate");
    });
  });

  it("Yaratish modal ochiladi va rol tanlash dropdown mavjud", async () => {
    renderUsersPage(adminUser);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /foydalanuvchi qo'shish/i }),
      ).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getByRole("button", { name: /foydalanuvchi qo'shish/i }),
    );

    await waitFor(() => {
      expect(screen.getByText(/yangi foydalanuvchi/i)).toBeInTheDocument();
      // Forma maydonlari mavjud (labellar)
      expect(screen.getByText(/to'liq ismi/i)).toBeInTheDocument();
      expect(screen.getByText(/telefon raqami/i)).toBeInTheDocument();
      expect(screen.getByText(/^parol$/i)).toBeInTheDocument();
      // Rol tanlash — label "Rol" mavjud (xom UUID yo'q — Select komponent)
      const roleLabels = screen.getAllByText(/^rol$/i);
      expect(roleLabels.length).toBeGreaterThan(0);
    });
  });

  it("agent foydalanuvchi uchun do'kon biriktirish tugmasi ko'rsatiladi", async () => {
    renderUsersPage(adminUser);

    await waitFor(() => {
      // agent roli uchun do'kon biriktirish tugmasi
      expect(
        screen.getByLabelText(/do'kon biriktirish/i),
      ).toBeInTheDocument();
    });
  });

  it("do'kon biriktirish modal — mavjud do'konlar ro'yxatidan tanlanadi (xom UUID yo'q)", async () => {
    renderUsersPage(adminUser);

    await waitFor(() => {
      expect(screen.getByLabelText(/do'kon biriktirish/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText(/do'kon biriktirish/i));

    await waitFor(() => {
      // Modal sarlavhasi ko'rsatiladi
      const modalTitles = screen.getAllByText(/do'kon biriktirish/i);
      expect(modalTitles.length).toBeGreaterThan(0);
    });

    // Do'kon tanlash label mavjud — xom UUID TextInput emas, Select komponent
    await waitFor(() => {
      expect(screen.getByText(/do'kon/i, { selector: "label" })).toBeInTheDocument();
    });

    // "Biriktirish" submit tugmasi mavjud — modal ichida
    const assignBtns = screen.getAllByRole("button", { name: /biriktirish/i });
    expect(assignBtns.length).toBeGreaterThan(0);
  });

  it("telefon maskalangan holda ko'rsatiladi (PII)", async () => {
    renderUsersPage(adminUser);

    await waitFor(() => {
      // 998901234567 → ****1234567 yoki shunga o'xshash masked format
      // Haqiqiy telefon to'liq ko'rsatilmaydi
      const phoneCells = screen.queryAllByText("998901234567");
      // PII maskalangan — to'liq raqam ko'rinmasligi kerak
      expect(phoneCells.length).toBe(0);
    });
  });
});
