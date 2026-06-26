/**
 * SetPriceModal — mahsulotga narx o'rnatish modali.
 *
 * POST /catalog/products/{id}/prices
 * Body: { segment_id, price, currency: "UZS", valid_from }
 */

import {
  Button,
  Group,
  Modal,
  NumberInput,
  Select,
  Stack,
  Text,
} from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useForm } from "@mantine/form";
import { useTranslation } from "react-i18next";
import { usePriceSegments, useSetPrice } from "../api/catalogApi";
import { useApiError } from "@/hooks/useApiError";
import type { ProductOut } from "@/api/types";

interface SetPriceModalProps {
  opened: boolean;
  onClose: () => void;
  product: ProductOut | null;
}

interface SetPriceFormValues {
  segment_id: string;
  price: number | string;
  valid_from: Date | null;
}

export function SetPriceModal({
  opened,
  onClose,
  product,
}: SetPriceModalProps) {
  const { t, i18n } = useTranslation();
  const { showError, showSuccess } = useApiError();
  const { data: segments = [] } = usePriceSegments();
  const setPrice = useSetPrice();

  const productName = product
    ? i18n.language === "ru"
      ? product.name_ru || product.name_uz
      : product.name_uz
    : "";

  const form = useForm<SetPriceFormValues>({
    initialValues: {
      segment_id: "",
      price: "",
      valid_from: new Date(),
    },
    validate: {
      segment_id: (v) =>
        !v ? t("catalog.set_price.segment_required", { defaultValue: "Segment tanlang" }) : null,
      price: (v) =>
        !v || Number(v) <= 0
          ? t("catalog.set_price.price_required", { defaultValue: "Narx 0 dan katta bo'lishi kerak" })
          : null,
      valid_from: (v) =>
        !v ? t("catalog.set_price.valid_from_required", { defaultValue: "Sanani kiriting" }) : null,
    },
  });

  const handleClose = () => {
    form.reset();
    onClose();
  };

  const handleSubmit = async (values: SetPriceFormValues) => {
    if (!product || !values.valid_from) return;
    try {
      await setPrice.mutateAsync({
        id: product.id,
        data: {
          segment_id: values.segment_id,
          price: Number(values.price),
          currency: "UZS",
          valid_from: values.valid_from.toISOString().split("T")[0],
        },
      });
      showSuccess("catalog.messages.price_set");
      handleClose();
    } catch (err) {
      showError(err);
    }
  };

  const segmentOptions = segments.map((s) => ({
    value: s.id,
    label: s.name,
  }));

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={
        <Text fw={600}>
          {t("catalog.set_price.title", { defaultValue: "Narx o'rnatish" })}
          {product && (
            <Text component="span" c="dimmed" size="sm" ml="xs">
              — {productName}
            </Text>
          )}
        </Text>
      }
      size="sm"
      centered
    >
      <form onSubmit={form.onSubmit((v) => { void handleSubmit(v); })}>
        <Stack gap="sm">
          <Select
            label={t("catalog.set_price.segment_label", { defaultValue: "Narx segmenti" })}
            placeholder={t("catalog.set_price.segment_placeholder", { defaultValue: "Segment tanlang" })}
            data={segmentOptions}
            required
            {...form.getInputProps("segment_id")}
          />
          <NumberInput
            label={t("catalog.set_price.price_label", { defaultValue: "Narx (UZS)" })}
            placeholder="0"
            required
            min={1}
            step={100}
            thousandSeparator=" "
            {...form.getInputProps("price")}
          />
          <DateInput
            label={t("catalog.set_price.valid_from_label", { defaultValue: "Amal qilish boshlanish sanasi" })}
            placeholder={t("catalog.set_price.valid_from_placeholder", { defaultValue: "Sanani tanlang" })}
            required
            valueFormat="YYYY-MM-DD"
            {...form.getInputProps("valid_from")}
          />
          <Group justify="flex-end" mt="md">
            <Button
              variant="subtle"
              onClick={handleClose}
              disabled={setPrice.isPending}
            >
              {t("common.cancel")}
            </Button>
            <Button type="submit" loading={setPrice.isPending}>
              {t("catalog.set_price.submit_btn", { defaultValue: "Saqlash" })}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
