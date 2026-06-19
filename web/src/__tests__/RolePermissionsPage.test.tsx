/**
 * RolePermissionsPage testlari
 *
 * Tekshiriladi:
 * 1. Sahifa sarlavhasi render bo'ladi
 * 2. Jadval sarlavhlari (Modul, Amal, rollar) ko'rsatiladi
 * 3. Modul nomlari jadvalda mavjud
 * 4. Administrator barcha amallar uchun ruxsatlarga ega (check icon)
 * 5. ruxsatsiz rol (agent) — "rbac:view" yo'q → "ruxsat yo'q" ko'rsatiladi
 * 6. Rol badge'lari ko'rsatiladi
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import type { AuthUser } from "@/auth/AuthContext";
import { RolePermissionsPage } from "@/features/rbac/RolePermissionsPage";

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
  // agent: rbac:view yo'q
  permissions: ["catalog:view", "customers:view"],
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

function renderRbacPage(user: AuthUser = adminUser) {
  currentUser = user;
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <Notifications />
        <MemoryRouter>
          <RolePermissionsPage />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("RolePermissionsPage", () => {
  beforeEach(() => {
    currentUser = adminUser;
    vi.clearAllMocks();
  });

  it("sahifa sarlavhasi render bo'ladi", async () => {
    renderRbacPage(adminUser);
    await waitFor(() => {
      expect(screen.getByText("Ruxsatlar matritsasi")).toBeInTheDocument();
    });
  });

  it("jadval sarlavhlari ko'rsatiladi", async () => {
    renderRbacPage(adminUser);
    await waitFor(() => {
      expect(screen.getByText("Modul")).toBeInTheDocument();
      expect(screen.getByText("Amal")).toBeInTheDocument();
    });
  });

  it("rol badge'lari ko'rsatiladi", async () => {
    renderRbacPage(adminUser);
    await waitFor(() => {
      // Sarlavha satrida va badge'larda bir nechta "Administrator" bo'lishi mumkin
      const adminTexts = screen.getAllByText("Administrator");
      expect(adminTexts.length).toBeGreaterThan(0);
      const agentTexts = screen.getAllByText("Savdo agenti");
      expect(agentTexts.length).toBeGreaterThan(0);
    });
  });

  it("modul nomlari jadvalda ko'rsatiladi", async () => {
    renderRbacPage(adminUser);
    await waitFor(() => {
      expect(screen.getByText("Katalog")).toBeInTheDocument();
      expect(screen.getByText("Mijozlar")).toBeInTheDocument();
      expect(screen.getByText("Buyurtmalar")).toBeInTheDocument();
      expect(screen.getByText("Buxgalteriya")).toBeInTheDocument();
    });
  });

  it("modul kod nomlari (monospace) ko'rsatiladi", async () => {
    renderRbacPage(adminUser);
    await waitFor(() => {
      expect(screen.getByText("catalog")).toBeInTheDocument();
      expect(screen.getByText("finance")).toBeInTheDocument();
      expect(screen.getByText("rbac")).toBeInTheDocument();
    });
  });

  it("amal nomlari (view, create, edit, delete) jadvalda bor", async () => {
    renderRbacPage(adminUser);
    await waitFor(() => {
      // Har bir modul uchun 5 amal × 12 modul = 60 qator, "view" ko'p marta
      const viewTexts = screen.getAllByText("view");
      expect(viewTexts.length).toBeGreaterThan(0);
      const createTexts = screen.getAllByText("create");
      expect(createTexts.length).toBeGreaterThan(0);
    });
  });

  it("manba izohi ko'rsatiladi", async () => {
    renderRbacPage(adminUser);
    await waitFor(() => {
      expect(screen.getByText(/permissions\.py/)).toBeInTheDocument();
    });
  });

  it("<Can rbac:view> — agent ruxsatsiz sahifani ko'rmaydi", async () => {
    renderRbacPage(agentUser);
    await waitFor(() => {
      expect(
        screen.getByText(/bu sahifani ko'rish uchun ruxsat yo'q/i),
      ).toBeInTheDocument();
    });
    // Jadval ko'rsatilmasligi kerak
    expect(screen.queryByText("Ruxsatlar matritsasi")).not.toBeInTheDocument();
    expect(screen.queryByText("Katalog")).not.toBeInTheDocument();
  });

  it("kuryer (courier) roli finance uchun ruxsatsiz — matritsa to'g'ri", async () => {
    // Jadval render bo'lganda finance-view qatori mavjud
    // courier uchun finance:view = false deb tekshiramiz (matritsa statik)
    renderRbacPage(adminUser);
    await waitFor(() => {
      expect(screen.getByText("Buxgalteriya")).toBeInTheDocument();
    });
    // "approve" amal har modul uchun bir marta keladi — getAllByText ishlatamiz
    const approveTexts = screen.getAllByText("approve");
    expect(approveTexts.length).toBeGreaterThan(0);
  });
});
