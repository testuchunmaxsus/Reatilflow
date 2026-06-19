/**
 * TicketsListPage testlari
 *
 * Tekshiriladi:
 * 1. Sahifa render bo'ladi va jadval sarlavhalari ko'rsatiladi
 * 2. Murojaatlar ro'yxati (mock API) jadvalda ko'rinadi
 * 3. Status badge to'g'ri ko'rsatiladi
 * 4. Yaratish tugmasi — view ruxsati borlar ko'radi
 * 5. <Can tickets:view> — ruxsatsiz rol sahifani ko'rmaydi
 * 6. Bo'sh holat ko'rsatiladi
 * 7. Xabar qo'shish — detail modal ochiladi va xabar yuboriladi
 * 8. Holat o'zgartirish — faqat admin/accountant ko'radi (tickets:edit)
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import type { AuthUser } from "@/auth/AuthContext";

// ─── Mock ma'lumotlar ─────────────────────────────────────────────────────────

const mockTickets = {
  items: [
    {
      id: "ticket-001",
      store_id: "store-uuid-001",
      author_id: "user-001",
      ticket_type: "taklif",
      subject: "Yangi mahsulot taklifi",
      body: "Mahsulot assortimentini kengaytirish taklif qilinadi",
      status: "new",
      assigned_to: null,
      branch_id: null,
      client_uuid: null,
      version: 1,
      created_at: "2026-06-01T10:00:00Z",
      updated_at: "2026-06-01T10:00:00Z",
      deleted_at: null,
      messages: null,
    },
    {
      id: "ticket-002",
      store_id: null,
      author_id: "user-002",
      ticket_type: "etiroz",
      subject: "Yetkazish muddati bo'yicha shikoyat",
      body: "Buyurtma o'z vaqtida yetkazilmadi",
      status: "in_progress",
      assigned_to: null,
      branch_id: null,
      client_uuid: null,
      version: 2,
      created_at: "2026-06-02T10:00:00Z",
      updated_at: "2026-06-02T12:00:00Z",
      deleted_at: null,
      messages: null,
    },
  ],
  total: 2,
  limit: 20,
  offset: 0,
};

const mockTicketDetail = {
  ...mockTickets.items[0],
  messages: [
    {
      id: "msg-001",
      ticket_id: "ticket-001",
      author_id: "user-001",
      body: "Dastlabki xabar",
      attachment_url: null,
      created_at: "2026-06-01T10:05:00Z",
    },
  ],
};

const mockTicketsEmpty = { items: [], total: 0, limit: 20, offset: 0 };

// ─── API mock ─────────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let ticketsResponse: any = mockTickets;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let ticketDetailResponse: any = mockTicketDetail;

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn((path: string) => {
        if (path.match(/\/tickets\/[^/]+$/)) return Promise.resolve(ticketDetailResponse);
        if (path.startsWith("/tickets")) return Promise.resolve(ticketsResponse);
        return Promise.resolve({});
      }),
      post: vi.fn(() =>
        Promise.resolve({
          id: "msg-new",
          ticket_id: "ticket-001",
          author_id: "admin-001",
          body: "Test xabar",
          attachment_url: null,
          created_at: "2026-06-19T10:00:00Z",
        }),
      ),
      patch: vi.fn(() => Promise.resolve({ ...mockTicketDetail, status: "in_progress" })),
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
    "tickets:view",
    "tickets:create",
    "tickets:edit",
    "tickets:delete",
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
  permissions: ["tickets:view", "tickets:create", "customers:view"],
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

import { TicketsListPage } from "@/features/tickets/TicketsListPage";

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
          <TicketsListPage />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("TicketsListPage", () => {
  beforeEach(() => {
    currentUser = adminUser;
    ticketsResponse = mockTickets;
    ticketDetailResponse = mockTicketDetail;
    vi.clearAllMocks();
  });

  it("jadval sarlavhalari render bo'ladi", async () => {
    renderPage(adminUser);

    await waitFor(() => {
      expect(screen.getByText(/mavzu/i)).toBeInTheDocument();
      // "Holat" sarlavhasi — th element ichida
      const holatTexts = screen.getAllByText(/^holat$/i);
      expect(holatTexts.length).toBeGreaterThan(0);
      expect(screen.getByText(/^sana$/i)).toBeInTheDocument();
    });
  });

  it("murojaatlar ro'yxati jadvalda ko'rsatiladi", async () => {
    renderPage(adminUser);

    await waitFor(() => {
      expect(
        screen.getByText("Yangi mahsulot taklifi"),
      ).toBeInTheDocument();
      expect(
        screen.getByText("Yetkazish muddati bo'yicha shikoyat"),
      ).toBeInTheDocument();
    });
  });

  it("status badge ko'rsatiladi (yangi, ko'rilmoqda)", async () => {
    renderPage(adminUser);

    await waitFor(() => {
      expect(screen.getByText("Yangi")).toBeInTheDocument();
      expect(screen.getByText("Ko'rilmoqda")).toBeInTheDocument();
    });
  });

  it("tip badge ko'rsatiladi (taklif, etiroz)", async () => {
    renderPage(adminUser);

    await waitFor(() => {
      expect(screen.getByText("Taklif")).toBeInTheDocument();
      expect(screen.getByText("Etiroz")).toBeInTheDocument();
    });
  });

  it("administrator uchun 'Murojaat yuborish' tugmasi ko'rinadi", async () => {
    renderPage(adminUser);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /murojaat yuborish/i }),
      ).toBeInTheDocument();
    });
  });

  it("<Can tickets:view> — ruxsatsiz rol sahifani ko'rmaydi", async () => {
    renderPage(noPermUser);

    await waitFor(() => {
      expect(
        screen.queryByText("Yangi mahsulot taklifi"),
      ).not.toBeInTheDocument();
      expect(
        screen.getByText(/bu sahifani ko'rish uchun ruxsat yo'q/i),
      ).toBeInTheDocument();
    });
  });

  it("bo'sh holat: 'Murojaatlar topilmadi' ko'rsatiladi", async () => {
    ticketsResponse = mockTicketsEmpty;
    renderPage(adminUser);

    await waitFor(() => {
      expect(screen.getByText(/murojaatlar topilmadi/i)).toBeInTheDocument();
    });
  });

  it("agent uchun 'Murojaat yuborish' tugmasi ko'rinadi (tickets:create bor)", async () => {
    renderPage(agentUser);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /murojaat yuborish/i }),
      ).toBeInTheDocument();
    });
  });

  it("Ko'rish tugmasi bosilganda detail modal ochiladi", async () => {
    renderPage(adminUser);

    await waitFor(() => {
      expect(
        screen.getByText("Yangi mahsulot taklifi"),
      ).toBeInTheDocument();
    });

    // Ko'rish tugmalaridan birinchisini bosing
    const viewBtns = screen.getAllByLabelText(/ko'rish/i);
    fireEvent.click(viewBtns[0]);

    await waitFor(() => {
      // Detail modal ochildi — xabar tarixi yoki murojaat matni ko'rsatilishi kerak
      expect(
        screen.getByText(/xabarlar/i),
      ).toBeInTheDocument();
    });
  });

  it("detail modal da xabar qo'shish va API /tickets/{id}/messages chaqiriladi", async () => {
    const { apiClient } = await import("@/api/client");
    renderPage(adminUser);

    await waitFor(() => {
      expect(
        screen.getByText("Yangi mahsulot taklifi"),
      ).toBeInTheDocument();
    });

    const viewBtns = screen.getAllByLabelText(/ko'rish/i);
    fireEvent.click(viewBtns[0]);

    // Xabar input topilishini kutamiz
    let textarea: HTMLElement | undefined;
    await waitFor(() => {
      textarea = screen.getByRole("textbox", {
        name: /yangi xabar/i,
      });
      expect(textarea).toBeInTheDocument();
    });

    fireEvent.change(textarea!, { target: { value: "Test xabar matni" } });

    // "Yuborish" tugmasi — "Murojaat yuborish" tugmasidan farq qiladi
    const sendBtns = screen.getAllByRole("button", { name: /^yuborish$/i });
    const sendBtn = sendBtns[0];
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/tickets/ticket-001/messages",
        expect.objectContaining({ body: "Test xabar matni" }),
      );
    });
  });

  it("detail modal da holat o'zgartirish — faqat admin ko'radi (tickets:edit)", async () => {
    renderPage(adminUser);

    await waitFor(() => {
      expect(
        screen.getByText("Yangi mahsulot taklifi"),
      ).toBeInTheDocument();
    });

    const viewBtns = screen.getAllByLabelText(/ko'rish/i);
    fireEvent.click(viewBtns[0]);

    await waitFor(() => {
      // Holat o'zgartirish bo'limi admin uchun ko'rinadi
      expect(
        screen.getByText(/holatni o'zgartirish/i),
      ).toBeInTheDocument();
    });
  });
});
