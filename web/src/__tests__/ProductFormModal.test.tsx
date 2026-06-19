/**
 * ProductFormModal testlari
 *
 * Tekshiriladi:
 * 1. Forma maydonlari render bo'ladi
 * 2. Majburiy maydonlar validatsiyasi: name_uz bo'sh bo'lsa xato ko'rsatiladi
 * 3. Submit: useMutation to'g'ri chaqiriladi
 * 4. Tahrirlash rejimi: mavjud qiymatlar to'ldirilgan
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import type { ProductOut } from "@/api/types";
import { ProductFormModal } from "@/features/catalog/components/ProductFormModal";

// ─── Mock mutation ────────────────────────────────────────────────────────────

const mockCreateMutateAsync = vi.fn();
const mockUpdateMutateAsync = vi.fn();

vi.mock("@/features/catalog/api/catalogApi", () => ({
  useCreateProduct: () => ({
    mutateAsync: mockCreateMutateAsync,
    isPending: false,
  }),
  useUpdateProduct: () => ({
    mutateAsync: mockUpdateMutateAsync,
    isPending: false,
  }),
  useCategories: () => ({ data: [], isLoading: false }),
}));

// ─── Render yordamchisi ───────────────────────────────────────────────────────

function renderProductFormModal(props: {
  opened: boolean;
  onClose: () => void;
  product?: ProductOut;
}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <Notifications />
        <ProductFormModal {...props} />
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("ProductFormModal", () => {
  const onClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockCreateMutateAsync.mockResolvedValue({ id: "new-prod" });
    mockUpdateMutateAsync.mockResolvedValue({ id: "prod-001" });
  });

  it("yaratish rejimida forma maydonlari render bo'ladi", () => {
    renderProductFormModal({ opened: true, onClose });

    // Mantine TextInput ni placeholder orqali topamiz
    expect(
      screen.getByPlaceholderText(/mahsulot nomini kiriting/i),
    ).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText(/введите название товара/i),
    ).toBeInTheDocument();
    // Yaratish rejimida "Yaratish" tugmasi bo'lishi kerak
    expect(
      screen.getByRole("button", { name: /^yaratish$/i }),
    ).toBeInTheDocument();
  });

  it("bo'sh forma submit bo'lganda mutasiya chaqirilmaydi", async () => {
    const user = userEvent.setup();
    renderProductFormModal({ opened: true, onClose });

    // Bo'sh forma bilan submit
    await user.click(screen.getByRole("button", { name: /^yaratish$/i }));

    // Validatsiya ishlaganida mutateAsync CHAQIRILMASLIGI kerak
    await waitFor(
      () => {
        // Mantine form validatsiyasi o'tsa mutateAsync chaqiriladi
        // O'tmasa — chaqirilmaydi. name_uz bo'sh bo'lgani uchun chaqirilmasligi kerak.
        expect(mockCreateMutateAsync).not.toHaveBeenCalled();
      },
      { timeout: 2000 },
    );
  });

  it("to'g'ri ma'lumotlar bilan createProduct.mutateAsync chaqiriladi", async () => {
    const user = userEvent.setup();
    renderProductFormModal({ opened: true, onClose });

    const nameUzInput = screen.getByPlaceholderText(
      /mahsulot nomini kiriting/i,
    );
    const nameRuInput = screen.getByPlaceholderText(
      /введите название товара/i,
    );

    await user.type(nameUzInput, "Non oq");
    await user.type(nameRuInput, "Хлеб белый");

    // SKU — BREAD-001 placeholder
    const skuInput = screen.getByPlaceholderText("BREAD-001");
    await user.type(skuInput, "MY-SKU-001");

    // Unit — comboboxlar orasidan unitni topish
    // "Tanlang..." placeholder qidiramiz
    const unitInputs = screen
      .getAllByRole("textbox")
      .filter((el) => el.getAttribute("placeholder") === "Tanlang...");
    if (unitInputs[0]) {
      await user.click(unitInputs[0]);
      const donaOption = await screen.findByText("Dona");
      await user.click(donaOption);
    }

    await user.click(screen.getByRole("button", { name: /^yaratish$/i }));

    await waitFor(
      () => {
        expect(mockCreateMutateAsync).toHaveBeenCalledWith(
          expect.objectContaining({
            name_uz: "Non oq",
            name_ru: "Хлеб белый",
            sku: "MY-SKU-001",
          }),
        );
      },
      { timeout: 3000 },
    );
  });

  it("tahrirlash rejimida mavjud qiymatlar to'ldirilgan bo'ladi", () => {
    const existingProduct: ProductOut = {
      id: "prod-001",
      name_uz: "Mavjud mahsulot",
      name_ru: "Существующий товар",
      sku: "EXIST-001",
      barcode: "1234567890",
      mxik_code: null,
      unit: "kg",
      category_id: "cat-001",
      photo_url: null,
      is_active: true,
      branch_scope: null,
      version: 1,
      created_at: "2026-06-16T10:00:00Z",
      updated_at: "2026-06-16T10:00:00Z",
    };

    renderProductFormModal({
      opened: true,
      onClose,
      product: existingProduct,
    });

    const nameUzInput = screen.getByPlaceholderText(
      /mahsulot nomini kiriting/i,
    ) as HTMLInputElement;
    expect(nameUzInput.value).toBe("Mavjud mahsulot");

    // Tahrirlash rejimida "Saqlash" tugmasi ko'rinadi
    expect(
      screen.getByRole("button", { name: /saqlash/i }),
    ).toBeInTheDocument();
  });
});
