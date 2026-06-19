/**
 * ProductFormModal — mahsulot yaratish / tahrirlash modal.
 *
 * RBAC: yaratish/tahrirlash tugmalari faqat catalog:create / catalog:edit ruxsati bilan.
 * i18n: uz/ru.
 * Mutation: POST /catalog/products yoki PATCH /catalog/products/{id}.
 * Validatsiya: Mantine useForm.
 */

import {
  Button,
  Checkbox,
  Group,
  Modal,
  Select,
  Stack,
  TextInput,
  Text,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useTranslation } from "react-i18next";
import { useCreateProduct, useUpdateProduct } from "../api/catalogApi";
import { useCategories } from "../api/catalogApi";
import { useApiError } from "@/hooks/useApiError";
import type { ProductOut } from "@/api/types";

// ─── Props ────────────────────────────────────────────────────────────────────

interface ProductFormModalProps {
  opened: boolean;
  onClose: () => void;
  /** Tahrirlanayotgan mahsulot — undefined bo'lsa yangi yaratiladi */
  product?: ProductOut;
}

// ─── Forma qiymatlari ─────────────────────────────────────────────────────────

interface ProductFormValues {
  name_uz: string;
  name_ru: string;
  sku: string;
  barcode: string;
  mxik_code: string;
  unit: string;
  category_id: string;
  is_active: boolean;
}

// ─── Komponent ────────────────────────────────────────────────────────────────

export function ProductFormModal({
  opened,
  onClose,
  product,
}: ProductFormModalProps) {
  const { t } = useTranslation();
  const { showError, showSuccess } = useApiError();
  const isEdit = Boolean(product);

  const createProduct = useCreateProduct();
  const updateProduct = useUpdateProduct();
  const { data: categories = [] } = useCategories();

  const form = useForm<ProductFormValues>({
    initialValues: {
      name_uz: product?.name_uz ?? "",
      name_ru: product?.name_ru ?? "",
      sku: product?.sku ?? "",
      barcode: product?.barcode ?? "",
      mxik_code: product?.mxik_code ?? "",
      unit: product?.unit ?? "",
      category_id: product?.category_id ?? "",
      is_active: product?.is_active ?? true,
    },
    validate: {
      name_uz: (v) =>
        v.trim().length === 0 ? t("catalog.form.name_uz_required") : null,
      name_ru: (v) =>
        v.trim().length === 0 ? t("catalog.form.name_ru_required") : null,
      sku: (v) =>
        v.trim().length === 0 ? t("catalog.form.sku_required") : null,
      unit: (v) =>
        v.trim().length === 0 ? t("catalog.form.unit_required") : null,
    },
  });

  // Forma yopilganda qayta bo'shatish
  const handleClose = () => {
    form.reset();
    onClose();
  };

  const handleSubmit = async (values: ProductFormValues) => {
    try {
      if (isEdit && product) {
        await updateProduct.mutateAsync({
          id: product.id,
          data: {
            name_uz: values.name_uz,
            name_ru: values.name_ru,
            sku: values.sku,
            barcode: values.barcode || null,
            mxik_code: values.mxik_code || null,
            unit: values.unit,
            category_id: values.category_id || null,
            is_active: values.is_active,
            version: product.version,
          },
        });
        showSuccess("catalog.messages.product_updated");
      } else {
        await createProduct.mutateAsync({
          name_uz: values.name_uz,
          name_ru: values.name_ru,
          sku: values.sku,
          barcode: values.barcode || null,
          mxik_code: values.mxik_code || null,
          unit: values.unit,
          category_id: values.category_id || null,
          is_active: values.is_active,
        });
        showSuccess("catalog.messages.product_created");
      }
      handleClose();
    } catch (error) {
      showError(error);
    }
  };

  const isPending = createProduct.isPending || updateProduct.isPending;

  const categoryData = categories.map((c) => ({
    value: c.id,
    label: c.name_uz,
  }));

  const unitOptions = [
    { value: "dona", label: t("catalog.units.dona") },
    { value: "kg", label: t("catalog.units.kg") },
    { value: "litr", label: t("catalog.units.litr") },
    { value: "m", label: t("catalog.units.m") },
    { value: "m2", label: t("catalog.units.m2") },
    { value: "m3", label: t("catalog.units.m3") },
    { value: "quti", label: t("catalog.units.quti") },
  ];

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={
        <Text fw={600}>
          {isEdit ? t("catalog.form.edit_title") : t("catalog.form.create_title")}
        </Text>
      }
      size="lg"
      centered
    >
      <form onSubmit={form.onSubmit((v) => { void handleSubmit(v); })}>
        <Stack gap="sm">
          <TextInput
            label={t("catalog.form.name_uz")}
            placeholder={t("catalog.form.name_uz_placeholder")}
            required
            {...form.getInputProps("name_uz")}
          />
          <TextInput
            label={t("catalog.form.name_ru")}
            placeholder={t("catalog.form.name_ru_placeholder")}
            required
            {...form.getInputProps("name_ru")}
          />
          <Group grow>
            <TextInput
              label={t("catalog.form.sku")}
              placeholder="BREAD-001"
              required
              {...form.getInputProps("sku")}
            />
            <TextInput
              label={t("catalog.form.barcode")}
              placeholder="4600001234567"
              {...form.getInputProps("barcode")}
            />
          </Group>
          <Group grow>
            <TextInput
              label={t("catalog.form.mxik_code")}
              placeholder="01234567"
              {...form.getInputProps("mxik_code")}
            />
            <Select
              label={t("catalog.form.unit")}
              placeholder={t("catalog.form.unit_placeholder")}
              data={unitOptions}
              required
              {...form.getInputProps("unit")}
            />
          </Group>
          <Select
            label={t("catalog.form.category")}
            placeholder={t("catalog.form.category_placeholder")}
            data={[{ value: "", label: t("catalog.form.no_category") }, ...categoryData]}
            clearable
            {...form.getInputProps("category_id")}
          />
          <Checkbox
            label={t("catalog.form.is_active")}
            {...form.getInputProps("is_active", { type: "checkbox" })}
          />
          <Group justify="flex-end" mt="md">
            <Button variant="subtle" onClick={handleClose} disabled={isPending}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" loading={isPending}>
              {isEdit ? t("common.save") : t("common.create")}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
