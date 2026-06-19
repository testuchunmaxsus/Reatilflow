/**
 * CreateOrderModal testlari — T11 himoyasi
 *
 * Tekshiriladi:
 * 1. Modal render bo'ladi
 * 2. Narx maydoni YO'Q (unit_price kiritish imkoniyati yo'q)
 * 3. Discount maydoni YO'Q (faqat product+qty)
 * 4. Segment maydoni YO'Q
 * 5. product_id va qty maydonlari mavjud
 * 6. Yuborilgan so'rovda faqat product_id + qty (narx/discount YUBORILMAYDI)
 * 7. Qator qo'shish tugmasi ishlaydi
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import type { AuthUser } from "@/auth/AuthContext";
import { CreateOrderModal } from "@/features/orders/components/CreateOrderModal";

// ─── API mock ─────────────────────────────────────────────────────────────────

const { mockPost } = vi.hoisted(() => ({ mockPost: vi.fn() }));

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn(() => Promise.resolve({})),
      post: mockPost,
      patch: vi.fn(() => Promise.resolve({})),
      delete: vi.fn(() => Promise.resolve(undefined)),
    },
    getAccessToken: vi.fn(() => null),
  };
});

// ─── Foydalanuvchi ────────────────────────────────────────────────────────────

const adminUser: AuthUser = {
  id: "admin-001",
  phone: "+998901234567",
  full_name: "Admin",
  role: "administrator",
  branch_id: null,
  locale: "uz",
  is_active: true,
  biometric_enrolled: false,
  permissions: ["orders:view", "orders:create", "orders:edit"],
};

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

function renderCreateModal(user: AuthUser = adminUser, onClose = vi.fn()) {
  currentUser = user;
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <Notifications />
        <MemoryRouter>
          <CreateOrderModal opened={true} onClose={onClose} />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("CreateOrderModal — T11 narx himoyasi", () => {
  beforeEach(() => {
    currentUser = adminUser;
    vi.clearAllMocks();
    mockPost.mockResolvedValue({
      id: "new-order-001",
      status: "confirmed",
      total_amount: "0",
      currency: "UZS",
      lines: [],
    });
  });

  it("modal render bo'ladi va asosiy maydonlar mavjud", async () => {
    renderCreateModal();
    expect(screen.getByText("Yangi buyurtma")).toBeInTheDocument();
    expect(screen.getByLabelText(/Do'kon ID/i)).toBeInTheDocument();
  });

  it("MUHIM: unit_price (narx) maydoni YO'Q — T11 himoyasi", () => {
    renderCreateModal();
    // unit_price, price, narx kabi maydon bo'lmasligi kerak
    expect(screen.queryByLabelText(/narx/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/unit.price/i)).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/narx/i)).not.toBeInTheDocument();
  });

  it("MUHIM: discount (chegirma) maydoni YO'Q — T11 himoyasi", () => {
    renderCreateModal();
    expect(screen.queryByLabelText(/chegirma/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/discount/i)).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/chegirma/i)).not.toBeInTheDocument();
  });

  it("MUHIM: segment maydoni YO'Q — T11 himoyasi", () => {
    renderCreateModal();
    expect(screen.queryByLabelText(/segment/i)).not.toBeInTheDocument();
  });

  it("product_id va qty maydonlari mavjud", async () => {
    renderCreateModal();
    // product_id input mavjud
    expect(screen.getByPlaceholderText("Mahsulot UUID")).toBeInTheDocument();
    // qty maydoni — Mantine NumberInput label orqali tekshiramiz
    expect(screen.getByText("Miqdor")).toBeInTheDocument();
  });

  it("server narx hisoblashi haqida izoh ko'rsatiladi", () => {
    renderCreateModal();
    expect(
      screen.getByText(/narx va chegirma server tomonidan/i),
    ).toBeInTheDocument();
  });

  it("yuborilgan so'rovda faqat store_id, mode, lines[{product_id, qty}] — narx/discount YO'Q", async () => {
    const user = userEvent.setup();
    renderCreateModal();

    // store_id kiritish
    const storeInput = screen.getByLabelText(/Do'kon ID/i);
    await user.clear(storeInput);
    await user.type(storeInput, "01900000-0000-7000-8000-000000000001");

    // product_id kiritish
    const productInput = screen.getByPlaceholderText("Mahsulot UUID");
    await user.clear(productInput);
    await user.type(productInput, "01900000-0000-7000-8000-000000000010");

    // Formani yuborish
    const submitBtn = screen.getByRole("button", { name: /buyurtma berish/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith(
        "/orders",
        expect.objectContaining({
          store_id: "01900000-0000-7000-8000-000000000001",
          lines: expect.arrayContaining([
            expect.objectContaining({
              product_id: "01900000-0000-7000-8000-000000000010",
              qty: expect.any(String),
              // unit_price va discount bo'lmasligi kerak
            }),
          ]),
        }),
      );
    });

    // unit_price va discount mavjud emasligini tekshirish
    const callArg = mockPost.mock.calls[0][1] as Record<string, unknown>;
    expect(callArg).not.toHaveProperty("unit_price");
    expect(callArg).not.toHaveProperty("discount");
    expect(callArg).not.toHaveProperty("segment_id");

    // lines qatorlarida ham narx bo'lmasligi kerak
    const lines = callArg.lines as Record<string, unknown>[];
    if (lines && lines.length > 0) {
      expect(lines[0]).not.toHaveProperty("unit_price");
      expect(lines[0]).not.toHaveProperty("discount");
    }
  });

  it("qator qo'shish tugmasi ishlaydi", async () => {
    const user = userEvent.setup();
    renderCreateModal();

    // Birinchi qator mavjud
    expect(screen.getAllByPlaceholderText("Mahsulot UUID")).toHaveLength(1);

    // Qator qo'shish
    const addBtn = screen.getByRole("button", { name: /qator qo'shish/i });
    await user.click(addBtn);

    // Endi ikkita qator bo'lishi kerak
    expect(screen.getAllByPlaceholderText("Mahsulot UUID")).toHaveLength(2);
  });
});
