/**
 * PromoFormModal — aksiya yaratish / tahrirlash modal.
 *
 * Yaratish: name_uz, name_ru, promo_type, rule_json, valid_from, valid_to,
 *           target_segment_id (Select), target_product_id (Select), is_active.
 * Tahrirlash: yuqoridagilar + version (optimistik lock).
 * rule_json: discount_percent YOKI discount_amount + ixtiyoriy min_qty.
 * target — mavjud ro'yxatdan Select (xom UUID emas).
 * SERVER-AVTORITAR: discount backend da hisoblanadi — UI faqat rule kiritadi.
 * RBAC: faqat administrator (backend ham tekshiradi).
 * i18n uz/ru.
 */

import {
  Button,
  Checkbox,
  Group,
  Modal,
  NumberInput,
  Select,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useForm } from "@mantine/form";
import { useTranslation } from "react-i18next";
import { useCreatePromo, useUpdatePromo, useSegmentOptions, useProductOptions } from "../api/promoApi";
import { useApiError } from "@/hooks/useApiError";
import { toLocalYMD, parseYMD } from "@/utils/date";
import type { PromoOut, RuleJson } from "../types";

// ─── Props ────────────────────────────────────────────────────────────────────

interface PromoFormModalProps {
  opened: boolean;
  onClose: () => void;
  promo?: PromoOut;
}

// ─── Forma qiymatlari ─────────────────────────────────────────────────────────

type DiscountMode = "percent" | "amount";

interface PromoFormValues {
  name_uz: string;
  name_ru: string;
  promo_type: string;
  discount_mode: DiscountMode;
  discount_value: number | "";
  min_qty: number | "";
  /** YYYY-MM-DD string */
  valid_from: string;
  /** YYYY-MM-DD string */
  valid_to: string;
  target_segment_id: string;
  target_product_id: string;
  is_active: boolean;
}

// ─── Sana validatsiya yordamchisi ─────────────────────────────────────────────

function isValidDate(s: string): boolean {
  if (!s) return false;
  const re = /^\d{4}-\d{2}-\d{2}$/;
  if (!re.test(s)) return false;
  const d = new Date(s);
  return !isNaN(d.getTime());
}

// ─── rule_json → forma qiymatlari ────────────────────────────────────────────

function ruleToForm(
  rule: RuleJson,
): { mode: DiscountMode; value: number | "" } {
  if (rule.discount_percent !== undefined) {
    return { mode: "percent", value: rule.discount_percent };
  }
  if (rule.discount_amount !== undefined) {
    return { mode: "amount", value: rule.discount_amount };
  }
  return { mode: "percent", value: "" };
}

// ─── Forma qiymatlari → rule_json ────────────────────────────────────────────

function formToRule(
  mode: DiscountMode,
  value: number | "",
  minQty: number | "",
): RuleJson {
  const rule: RuleJson = {};
  if (mode === "percent" && value !== "") {
    rule.discount_percent = Number(value);
  } else if (mode === "amount" && value !== "") {
    rule.discount_amount = Number(value);
  }
  if (minQty !== "" && Number(minQty) > 0) {
    rule.min_qty = Number(minQty);
  }
  return rule;
}

// ─── Komponent ────────────────────────────────────────────────────────────────

export function PromoFormModal({
  opened,
  onClose,
  promo,
}: PromoFormModalProps) {
  const { t, i18n } = useTranslation();
  const { showError, showSuccess } = useApiError();
  const isEdit = Boolean(promo);

  const createPromo = useCreatePromo();
  const updatePromo = useUpdatePromo();
  const { data: segmentsData } = useSegmentOptions();
  const { data: productsData } = useProductOptions();

  // Segmentlar Select options (mavjud ro'yxatdan — xom UUID emas)
  const segmentOptions = [
    { value: "", label: t("promo.form.no_segment") },
    ...(segmentsData ?? []).map((s) => ({
      value: s.id,
      label: s.name,
    })),
  ];

  // Mahsulotlar Select options (mavjud ro'yxatdan — xom UUID emas)
  const productOptions = [
    { value: "", label: t("promo.form.no_product") },
    ...(productsData?.items ?? []).map((p) => ({
      value: p.id,
      label: i18n.language === "ru" ? p.name_ru : p.name_uz,
    })),
  ];

  const promoTypeOptions = [
    { value: "discount", label: t("promo.type.discount") },
    { value: "bonus", label: t("promo.type.bonus") },
    { value: "gift", label: t("promo.type.gift") },
  ];

  const discountModeOptions = [
    { value: "percent", label: t("promo.form.discount_percent") },
    { value: "amount", label: t("promo.form.discount_amount") },
  ];

  // rule_json dan boshlang'ich qiymatlar
  const initRule = promo?.rule_json
    ? ruleToForm(promo.rule_json)
    : { mode: "percent" as DiscountMode, value: "" as number | "" };

  const form = useForm<PromoFormValues>({
    initialValues: {
      name_uz: promo?.name_uz ?? "",
      name_ru: promo?.name_ru ?? "",
      promo_type: promo?.promo_type ?? "discount",
      discount_mode: initRule.mode,
      discount_value: initRule.value,
      min_qty: promo?.rule_json?.min_qty ?? "",
      valid_from: promo?.valid_from ?? "",
      valid_to: promo?.valid_to ?? "",
      target_segment_id: promo?.target_segment_id ?? "",
      target_product_id: promo?.target_product_id ?? "",
      is_active: promo?.is_active ?? true,
    },
    validate: {
      name_uz: (v) =>
        !v.trim() ? t("promo.form.name_uz_required") : null,
      name_ru: (v) =>
        !v.trim() ? t("promo.form.name_ru_required") : null,
      discount_value: (v) => {
        if (v === "" || v === undefined)
          return t("promo.form.discount_value_required");
        if (Number(v) <= 0) return t("promo.form.discount_value_positive");
        return null;
      },
      valid_from: (v) =>
        !isValidDate(v) ? t("promo.form.valid_from_required") : null,
      valid_to: (v, values) => {
        if (!isValidDate(v)) return t("promo.form.valid_to_required");
        if (values.valid_from && v < values.valid_from)
          return t("promo.form.valid_to_before_from");
        return null;
      },
    },
  });

  const handleClose = () => {
    form.reset();
    onClose();
  };

  const handleSubmit = async (values: PromoFormValues) => {
    const rule = formToRule(
      values.discount_mode,
      values.discount_value,
      values.min_qty,
    );

    try {
      if (isEdit && promo) {
        await updatePromo.mutateAsync({
          id: promo.id,
          data: {
            version: promo.version,
            name_uz: values.name_uz,
            name_ru: values.name_ru,
            promo_type: values.promo_type,
            rule_json: rule,
            valid_from: values.valid_from,
            valid_to: values.valid_to,
            target_segment_id: values.target_segment_id || null,
            target_product_id: values.target_product_id || null,
            is_active: values.is_active,
          },
        });
        showSuccess("promo.messages.updated");
      } else {
        await createPromo.mutateAsync({
          name_uz: values.name_uz,
          name_ru: values.name_ru,
          promo_type: values.promo_type,
          rule_json: rule,
          valid_from: values.valid_from,
          valid_to: values.valid_to,
          target_segment_id: values.target_segment_id || null,
          target_product_id: values.target_product_id || null,
          is_active: values.is_active,
        });
        showSuccess("promo.messages.created");
      }
      handleClose();
    } catch (err) {
      showError(err);
    }
  };

  const isPending = createPromo.isPending || updatePromo.isPending;

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={
        <Text fw={600}>
          {isEdit ? t("promo.form.edit_title") : t("promo.form.create_title")}
        </Text>
      }
      size="lg"
      centered
    >
      <form onSubmit={form.onSubmit((v) => { void handleSubmit(v); })}>
        <Stack gap="sm">
          <Group grow>
            <TextInput
              label={t("promo.form.name_uz")}
              placeholder={t("promo.form.name_uz_placeholder")}
              required
              {...form.getInputProps("name_uz")}
            />
            <TextInput
              label={t("promo.form.name_ru")}
              placeholder={t("promo.form.name_ru_placeholder")}
              required
              {...form.getInputProps("name_ru")}
            />
          </Group>

          <Select
            label={t("promo.form.promo_type")}
            data={promoTypeOptions}
            {...form.getInputProps("promo_type")}
            allowDeselect={false}
          />

          {/* rule_json maydonlari — SERVER-AVTORITAR eslatma */}
          <Text size="xs" c="dimmed">
            {t("promo.form.rule_note")}
          </Text>
          <Group grow>
            <Select
              label={t("promo.form.discount_mode")}
              data={discountModeOptions}
              {...form.getInputProps("discount_mode")}
              allowDeselect={false}
            />
            <NumberInput
              label={
                form.values.discount_mode === "percent"
                  ? t("promo.form.discount_percent_label")
                  : t("promo.form.discount_amount_label")
              }
              placeholder={
                form.values.discount_mode === "percent" ? "10" : "5000"
              }
              min={0}
              max={form.values.discount_mode === "percent" ? 100 : undefined}
              required
              {...form.getInputProps("discount_value")}
            />
            <NumberInput
              label={t("promo.form.min_qty")}
              placeholder="1"
              min={0}
              {...form.getInputProps("min_qty")}
            />
          </Group>

          <Group grow>
            <DateInput
              label={t("promo.form.valid_from")}
              placeholder="2026-01-01"
              valueFormat="YYYY-MM-DD"
              required
              value={parseYMD(form.values.valid_from)}
              onChange={(date) =>
                form.setFieldValue(
                  "valid_from",
                  date ? toLocalYMD(date) : "",
                )
              }
              error={form.errors.valid_from}
            />
            <DateInput
              label={t("promo.form.valid_to")}
              placeholder="2027-01-01"
              valueFormat="YYYY-MM-DD"
              required
              value={parseYMD(form.values.valid_to)}
              onChange={(date) =>
                form.setFieldValue(
                  "valid_to",
                  date ? toLocalYMD(date) : "",
                )
              }
              error={form.errors.valid_to}
            />
          </Group>

          {/* Target — mavjud ro'yxatdan Select (xom UUID emas) */}
          <Group grow>
            <Select
              label={t("promo.form.target_segment")}
              data={segmentOptions}
              {...form.getInputProps("target_segment_id")}
              searchable
              allowDeselect={false}
            />
            <Select
              label={t("promo.form.target_product")}
              data={productOptions}
              {...form.getInputProps("target_product_id")}
              searchable
              allowDeselect={false}
            />
          </Group>

          <Checkbox
            label={t("promo.form.is_active")}
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
