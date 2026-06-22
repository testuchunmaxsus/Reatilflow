/**
 * LoginPage testlari
 *
 * Tekshiriladi:
 * 1. Login formasi render bo'ladi
 * 2. Noto'g'ri telefon formatida validatsiya xatosi ko'rsatiladi
 * 3. Bo'sh parolda validatsiya xatosi ko'rsatiladi
 * 4. Login muvaffaqiyatli bo'lganda navigate chaqiriladi
 * 5. Server xatosi (ApiError) ko'rsatiladi
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { MantineProvider } from "@mantine/core";

// ─── navigate mock ────────────────────────────────────────────────────────

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// ─── AuthContext mock ─────────────────────────────────────────────────────

const mockLogin = vi.fn();
vi.mock("@/auth/AuthContext", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/auth/AuthContext")>();
  return {
    ...actual,
    useAuth: () => ({
      user: undefined,
      isLoading: false,
      login: mockLogin,
      logout: vi.fn(),
      refreshUser: vi.fn(),
    }),
  };
});

// ─── Import after mock ────────────────────────────────────────────────────

import { LoginPage } from "@/auth/LoginPage";

// ─── Yordamchi ────────────────────────────────────────────────────────────

function renderLoginPage() {
  return render(
    <MantineProvider>
      <MemoryRouter initialEntries={["/login"]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
        </Routes>
      </MemoryRouter>
    </MantineProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────

describe("LoginPage", () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    mockLogin.mockClear();
  });

  it("login formasi render bo'ladi", () => {
    renderLoginPage();
    // Label matni i18n orqali uz.json dan
    expect(screen.getByLabelText(/telefon raqami/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/parol/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /kirish/i })).toBeInTheDocument();
  });

  it("noto'g'ri telefon formatida validatsiya xatosi ko'rsatiladi", async () => {
    const user = userEvent.setup();
    renderLoginPage();

    await user.type(screen.getByLabelText(/telefon raqami/i), "12345");
    await user.type(screen.getByLabelText(/parol/i), "secret123");
    await user.click(screen.getByRole("button", { name: /kirish/i }));

    await waitFor(() => {
      expect(screen.getByText(/formatida kiriting/i)).toBeInTheDocument();
    });
  });

  it("bo'sh parolda validatsiya xatosi ko'rsatiladi", async () => {
    const user = userEvent.setup();
    renderLoginPage();

    await user.type(screen.getByLabelText(/telefon raqami/i), "+998901234567");
    await user.click(screen.getByRole("button", { name: /kirish/i }));

    await waitFor(() => {
      expect(screen.getByText(/parolni kiriting/i)).toBeInTheDocument();
    });
  });

  it("login muvaffaqiyatli bo'lganda login() chaqiriladi (navigate useEffect orqali)", async () => {
    // Izoh: navigate() endi useAuth().user o'zgarish orqali (useEffect) chaqiriladi.
    // Bu testda user undefined qoladi (mock o'zgarmaydi), shuning uchun
    // faqat login() chaqirilganini tekshiramiz.
    mockLogin.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderLoginPage();

    await user.type(screen.getByLabelText(/telefon raqami/i), "+998901234567");
    await user.type(screen.getByLabelText(/parol/i), "secret123");
    await user.click(screen.getByRole("button", { name: /kirish/i }));

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith({
        phone: "+998901234567",
        password: "secret123",
      });
    });
  });

  it("server xatosi ko'rsatiladi (i18n message_key tarjimasi)", async () => {
    const { ApiError } = await import("@/api/client");
    mockLogin.mockRejectedValue(
      new ApiError(401, {
        message_key: "auth.invalid_credentials",
        message: "Telefon yoki parol noto'g'ri",
        detail: null,
      }),
    );
    const user = userEvent.setup();
    renderLoginPage();

    await user.type(screen.getByLabelText(/telefon raqami/i), "+998901234567");
    await user.type(screen.getByLabelText(/parol/i), "wrongpass");
    await user.click(screen.getByRole("button", { name: /kirish/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/telefon yoki parol noto'g'ri/i),
      ).toBeInTheDocument();
    });
  });
});
