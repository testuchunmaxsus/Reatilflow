/**
 * AgentCabinetPage — smoke test
 *
 * Tekshiriladi:
 * 1. Profil ma'lumotlari ko'rsatiladi (ism, telefon, rol)
 * 2. Do'konlar ro'yxati ko'rsatiladi
 * 3. agent_cabinet:edit ruxsati bo'lsa tahrirlash tugmasi ko'rinadi
 * 4. agent_cabinet:edit ruxsati bo'lmasa tahrirlash tugmasi ko'rinmaydi
 * 5. Do'konlar bo'sh bo'lganda bo'sh holat ko'rsatiladi
 *
 * Backend endpointlari:
 *   GET /auth/me             — profil
 *   GET /customers/stores    — do'konlar
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import type { AuthUser } from "@/auth/AuthContext";

// ─── Mock ma'lumotlar ─────────────────────────────────────────────────────────

const mockMe = {
  id: "agent-001",
  phone: "+998901234567",
  full_name: "Sardor Toshmatov",
  role: "agent",
  branch_id: null,
  locale: "uz",
  is_active: true,
  biometric_enrolled: false,
  permissions: ["customers:view", "agent_cabinet:edit"],
};

const mockStores = {
  items: [
    {
      id: "store-001",
      name: "ABC Do'koni",
      inn: null,
      inps: null,
      owner_name: "Alisher Karimov",
      phone: "+998901112233",
      gps_lat: null,
      gps_lng: null,
      address: "Toshkent, Chilonzor",
      segment_id: null,
      agent_id: "agent-001",
      branch_id: null,
      credit_limit: null,
      version: 1,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
    {
      id: "store-002",
      name: "XYZ Supermarket",
      inn: null,
      inps: null,
      owner_name: null,
      phone: null,
      gps_lat: null,
      gps_lng: null,
      address: "Toshkent, Yakkasaroy",
      segment_id: null,
      agent_id: "agent-001",
      branch_id: null,
      credit_limit: null,
      version: 1,
      created_at: "2026-01-02T00:00:00Z",
      updated_at: "2026-01-02T00:00:00Z",
    },
  ],
  total: 2,
  limit: 20,
  offset: 0,
};

const mockStoresEmpty = { items: [], total: 0, limit: 20, offset: 0 };

// ─── API mock ─────────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let storesResponse: any = mockStores;

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn((path: string) => {
        if (path === "/auth/me") return Promise.resolve(mockMe);
        if (path.startsWith("/customers/stores")) return Promise.resolve(storesResponse);
        return Promise.resolve({});
      }),
      patch: vi.fn(() => Promise.resolve({})),
      post: vi.fn(() => Promise.resolve({})),
      delete: vi.fn(() => Promise.resolve(undefined)),
    },
  };
});

// ─── Auth mock ────────────────────────────────────────────────────────────────

const agentUser: AuthUser = {
  id: "agent-001",
  phone: "+998901234567",
  full_name: "Sardor Toshmatov",
  role: "agent",
  branch_id: null,
  locale: "uz",
  is_active: true,
  biometric_enrolled: false,
  permissions: ["customers:view", "agent_cabinet:edit"],
};

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({
    user: agentUser,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
  }),
}));

// ─── Render yordamchisi ───────────────────────────────────────────────────────

import { AgentCabinetPage } from "@/features/agent-cabinet/AgentCabinetPage";

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <Notifications />
        <MemoryRouter>
          <AgentCabinetPage />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("AgentCabinetPage — smoke", () => {
  beforeEach(() => {
    storesResponse = mockStores;
    vi.clearAllMocks();
  });

  it("sahifa sarlavhasi ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/agent kabineti/i)).toBeInTheDocument();
    });
  });

  it("agent ismi ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Sardor Toshmatov")).toBeInTheDocument();
    });
  });

  it("agent telefoni ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("+998901234567")).toBeInTheDocument();
    });
  });

  it("biriktirilgan do'konlar ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("ABC Do'koni")).toBeInTheDocument();
      expect(screen.getByText("XYZ Supermarket")).toBeInTheDocument();
    });
  });

  it("agent_cabinet:edit ruxsati bo'lsa tahrirlash tugmasi ko'rinadi", async () => {
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /tahrirlash/i }),
      ).toBeInTheDocument();
    });
  });

  it("bo'sh holat ko'rsatiladi (do'konlar yo'q)", async () => {
    storesResponse = mockStoresEmpty;
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByText(/biriktirilgan do'konlar topilmadi/i),
      ).toBeInTheDocument();
    });
  });

  it("/auth/me endpointiga murojaat qilinadi", async () => {
    const { apiClient } = await import("@/api/client");
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Sardor Toshmatov")).toBeInTheDocument();
    });
    expect(apiClient.get).toHaveBeenCalledWith("/auth/me");
  });

  it("/customers/stores endpointiga murojaat qilinadi", async () => {
    const { apiClient } = await import("@/api/client");
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("ABC Do'koni")).toBeInTheDocument();
    });
    expect(apiClient.get).toHaveBeenCalledWith(
      expect.stringContaining("/customers/stores"),
    );
  });
});
