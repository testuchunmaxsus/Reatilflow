/**
 * ImportPage va AssistantWidget testlari.
 *
 * Tekshiriladi:
 * 1. ImportPage — ruxsatsiz foydalanuvchi "ruxsat yo'q" xabari
 * 2. ImportPage — ruxsatli foydalanuvchi sahifani ko'radi, tab'lar ko'rinadi
 * 3. ImportPage — Excel yuklash → preview jadval ko'rinadi
 * 4. ImportPage — preview bo'sh bo'lsa tasdiqlash tugmasi mavjud emas
 * 5. ImportPage — confirm muvaffaqiyatli → natija ko'rinadi
 * 6. AssistantWidget — assistant:view ruxsati yo'q → widget ko'rinmaydi
 * 7. AssistantWidget — ruxsatli → tugma ko'rinadi
 * 8. AssistantWidget — tugma bosilsa chat paneli ochiladi
 * 9. AssistantWidget — xabar yuborilganda javob qo'shiladi
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import type { AuthUser } from "@/auth/AuthContext";

// ─── Mock ma'lumotlar ─────────────────────────────────────────────────────────

const mockExcelParseOut = {
  columns_detected: [
    { source_header: "Nomi", mapped_to: "name", confidence: 0.95 },
    { source_header: "Miqdor", mapped_to: "qty", confidence: 0.90 },
    { source_header: "Narx", mapped_to: "price", confidence: 0.88 },
  ],
  rows: [
    {
      name: "Mahsulot A",
      sku: "SKU-001",
      barcode: null,
      qty: 10,
      price: 50000,
      currency: "UZS",
      expiry_date: null,
      row_index: 2,
    },
    {
      name: "Mahsulot B",
      sku: null,
      barcode: "1234567890",
      qty: 5,
      price: 120000,
      currency: "UZS",
      expiry_date: "2026-12-31",
      row_index: 3,
    },
  ],
  warnings: [],
  parse_id: "parse-uuid-001",
};

const mockConfirmOut = {
  created: 2,
  skipped: 0,
  errors: [],
  target: "catalog" as const,
};

const mockChatOut = {
  reply: "Salom! Katalog modulida mahsulot qo'shish uchun...",
  ai_enabled: true,
};

// ─── API mock ─────────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let parseResponse: any = mockExcelParseOut;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let confirmResponse: any = mockConfirmOut;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let chatResponse: any = mockChatOut;

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      upload: vi.fn(() => Promise.resolve(parseResponse)),
      post: vi.fn((path: string) => {
        if (path === "/import/confirm") return Promise.resolve(confirmResponse);
        if (path === "/assistant/chat") return Promise.resolve(chatResponse);
        return Promise.resolve({});
      }),
      get: vi.fn(() => Promise.resolve({})),
    },
  };
});

// ─── Auth mock ────────────────────────────────────────────────────────────────

// import:create + assistant:view ruxsatli administrator
const adminUser: AuthUser = {
  id: "admin-001",
  phone: "+998901234567",
  full_name: "Admin Test",
  role: "administrator",
  branch_id: null,
  locale: "uz",
  is_active: true,
  biometric_enrolled: false,
  permissions: [
    "import:view",
    "import:create",
    "assistant:view",
    "catalog:view",
  ],
};

// Ruxsatsiz foydalanuvchi
const noPermUser: AuthUser = {
  id: "user-002",
  phone: "+998901234568",
  full_name: "No Perm",
  role: "agent",
  branch_id: null,
  locale: "uz",
  is_active: true,
  biometric_enrolled: false,
  permissions: ["catalog:view"],
};

let mockUser: AuthUser = adminUser;

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({
    user: mockUser,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
  }),
}));

// ─── Render yordamchisi ───────────────────────────────────────────────────────

import { ImportPage } from "@/features/import/ImportPage";
import { AssistantWidget } from "@/features/assistant/AssistantWidget";

function renderImportPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <Notifications />
        <MemoryRouter>
          <ImportPage />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

function renderAssistantWidget() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <Notifications />
        <MemoryRouter>
          <AssistantWidget />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("ImportPage", () => {
  beforeEach(() => {
    mockUser = adminUser;
    parseResponse = mockExcelParseOut;
    confirmResponse = mockConfirmOut;
    vi.clearAllMocks();
  });

  it("ruxsatsiz foydalanuvchi 'ruxsat yo'q' ko'radi", async () => {
    mockUser = noPermUser;
    renderImportPage();
    await waitFor(() => {
      expect(
        screen.getByText(/ruxsat yo'q/i),
      ).toBeInTheDocument();
    });
  });

  it("ruxsatli foydalanuvchi sahifani ko'radi", async () => {
    renderImportPage();
    await waitFor(() => {
      // Sarlavha — h3 boshiga ko'ra
      expect(
        screen.getByRole("heading", { name: /import/i }),
      ).toBeInTheDocument();
    });
    // Excel tab ko'rinishi — role="tab" bilan aniq qidiruv
    expect(screen.getByRole("tab", { name: /excel/i })).toBeInTheDocument();
    // Nakladnoy tab ko'rinishi
    expect(screen.getByRole("tab", { name: /nakladnoy/i })).toBeInTheDocument();
  });

  it("boshlang'ich holat — preview bo'sh", async () => {
    renderImportPage();
    await waitFor(() => {
      expect(
        screen.getByText(/excel fayl tanlash/i),
      ).toBeInTheDocument();
    });
    // Tasdiqlash tugmasi dastlab ko'rinmaydi
    expect(screen.queryByText(/tasdiqlab import/i)).not.toBeInTheDocument();
  });

  it("Excel yuklanganda preview jadval ko'rinadi", async () => {
    renderImportPage();
    await waitFor(() => {
      expect(screen.getByText(/excel fayl tanlash/i)).toBeInTheDocument();
    });

    // Fayl input'ni topib o'zgartirish — accept .xlsx ga ega birinchi input
    const allFileInputs = document.querySelectorAll('input[type="file"]');
    // Excel tab panelida birinchi file input
    const excelInput = Array.from(allFileInputs)[0] as HTMLInputElement;
    expect(excelInput).toBeTruthy();

    const file = new File(["xlsx-content"], "test.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });

    Object.defineProperty(excelInput, "files", {
      value: { 0: file, length: 1, item: () => file },
      configurable: true,
    });
    fireEvent.change(excelInput);

    // Preview jadval ko'rinishi kerak
    await waitFor(
      () => {
        expect(screen.getAllByDisplayValue("Mahsulot A").length).toBeGreaterThan(0);
      },
      { timeout: 5000 },
    );
  });

  it("preview mavjud bo'lganda tasdiqlash tugmasi ko'rinadi", async () => {
    renderImportPage();
    await waitFor(() => {
      expect(screen.getByText(/excel fayl tanlash/i)).toBeInTheDocument();
    });

    const allFileInputs = document.querySelectorAll('input[type="file"]');
    const excelInput = Array.from(allFileInputs)[0] as HTMLInputElement;

    const file = new File(["data"], "products.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    Object.defineProperty(excelInput, "files", {
      value: { 0: file, length: 1, item: () => file },
      configurable: true,
    });
    fireEvent.change(excelInput);

    await waitFor(() => {
      expect(screen.getByText(/tasdiqlab import/i)).toBeInTheDocument();
    });
  });

  it("confirm muvaffaqiyatli → natija ko'rinadi", async () => {
    renderImportPage();
    await waitFor(() => {
      expect(screen.getByText(/excel fayl tanlash/i)).toBeInTheDocument();
    });

    // Fayl yuklash
    const allFileInputs = document.querySelectorAll('input[type="file"]');
    const excelInput = Array.from(allFileInputs)[0] as HTMLInputElement;

    const file = new File(["data"], "products.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    Object.defineProperty(excelInput, "files", {
      value: { 0: file, length: 1, item: () => file },
      configurable: true,
    });
    fireEvent.change(excelInput);

    await waitFor(() => {
      expect(screen.getByText(/tasdiqlab import/i)).toBeInTheDocument();
    });

    // Tasdiqlash
    fireEvent.click(screen.getByText(/tasdiqlab import/i));

    // "Import natijasi" bo'limi ko'rinishi kerak
    await waitFor(() => {
      expect(screen.getByText(/import natijasi/i)).toBeInTheDocument();
    });
    // Yaratildi badge — getAllByText (notification + badge ikki joyda bo'lishi mumkin)
    expect(screen.getAllByText(/yaratildi: 2/i).length).toBeGreaterThan(0);
  });

  it("noto'g'ri format (txt) — preview ko'rinmaydi", async () => {
    renderImportPage();
    await waitFor(() => {
      expect(screen.getByText(/excel fayl tanlash/i)).toBeInTheDocument();
    });

    const allFileInputs = document.querySelectorAll('input[type="file"]');
    const excelInput = Array.from(allFileInputs)[0] as HTMLInputElement;

    const badFile = new File(["text"], "bad.txt", { type: "text/plain" });
    Object.defineProperty(excelInput, "files", {
      value: { 0: badFile, length: 1, item: () => badFile },
      configurable: true,
    });
    fireEvent.change(excelInput);

    // Preview ko'rinmasligi kerak (format tekshiruvi xato beradi)
    await new Promise((r) => setTimeout(r, 200));
    expect(screen.queryByDisplayValue("Mahsulot A")).not.toBeInTheDocument();
  });
});

describe("AssistantWidget", () => {
  beforeEach(() => {
    mockUser = adminUser;
    chatResponse = mockChatOut;
    vi.clearAllMocks();
  });

  it("assistant:view ruxsati yo'q → widget ko'rinmaydi", async () => {
    mockUser = noPermUser;
    renderAssistantWidget();
    await new Promise((r) => setTimeout(r, 50));
    // Tugma ko'rinmasligi kerak
    expect(screen.queryByLabelText(/ai yordamchi/i)).not.toBeInTheDocument();
  });

  it("ruxsatli foydalanuvchi — suzuvchi tugma ko'rinadi", async () => {
    renderAssistantWidget();
    await waitFor(() => {
      expect(screen.getByLabelText(/ai yordamchi/i)).toBeInTheDocument();
    });
  });

  it("tugma bosilsa chat paneli ochiladi", async () => {
    renderAssistantWidget();
    await waitFor(() => {
      expect(screen.getByLabelText(/ai yordamchi/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText(/ai yordamchi/i));

    await waitFor(() => {
      // Salomlashuv xabari ko'rinishi kerak
      expect(
        screen.getByText(/salom!/i),
      ).toBeInTheDocument();
    });
  });

  it("xabar yozib Enter bosish — javob qo'shiladi", async () => {
    renderAssistantWidget();
    await waitFor(() => {
      expect(screen.getByLabelText(/ai yordamchi/i)).toBeInTheDocument();
    });

    // Panel ochish
    fireEvent.click(screen.getByLabelText(/ai yordamchi/i));

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/savol yozing/i)).toBeInTheDocument();
    });

    // Xabar yozish
    const input = screen.getByPlaceholderText(/savol yozing/i);
    fireEvent.change(input, { target: { value: "Katalog moduli nima?" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false });

    // Javob ko'rinishi kerak
    await waitFor(() => {
      expect(
        screen.getByText(/katalog modulida mahsulot qo'shish/i),
      ).toBeInTheDocument();
    });
  });

  it("yopish tugmasi bosilsa panel yopiladi", async () => {
    renderAssistantWidget();
    await waitFor(() => {
      expect(screen.getByLabelText(/ai yordamchi/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText(/ai yordamchi/i));

    await waitFor(() => {
      expect(screen.getByText(/salom!/i)).toBeInTheDocument();
    });

    // Yopish
    const closeBtn = screen.getByLabelText(/yopish/i);
    fireEvent.click(closeBtn);

    await waitFor(() => {
      expect(screen.queryByText(/salom!/i)).not.toBeInTheDocument();
    });
  });
});
