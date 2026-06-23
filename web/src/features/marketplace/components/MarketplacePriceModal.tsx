/**
 * MarketplacePriceModal — mahsulotni marketplace'ga nashr qilish.
 *
 * PATCH /catalog/products/{id}/marketplace
 * Narxni kiritib mahsulotni marketplace'ga publish qilish.
 * Server-avtoritar: narx majburiy emas lekin tavsiya etiladi.
 */

import {
  Button,
  Group,
  Modal,
  NumberInput,
  Stack,
  Text,
} from "@mantine/core";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { notifications } from "@mantine/notifications";
import { useToggleMarketplacePublish } from "../api/marketplaceApi";
import { useApiError } from "@/hooks/useApiError";
import type { ProductOut } from "@/api/types";

interface MarketplacePriceModalProps {
  opened: boolean;
  onClose: () => void;
  product: ProductOut | null;
}

export function MarketplacePriceModal({
  opened,
  onClose,
  product,
}: MarketplacePriceModalProps) {
  const { t, i18n } = useTranslation();
  const { showError } = useApiError();
  const [price, setPrice] = useState<number | string>("");
  const toggleMarketplace = useToggleMarketplacePublish();

  const productName = product
    ? i18n.language === "ru"
      ? product.name_ru || product.name_uz
      : product.name_uz
    : "";

  const handleClose = () => {
    setPrice("");
    onClose();
  };

  const handleSubmit = async () => {
    if (!product) return;
    try {
      await toggleMarketplace.mutateAsync({
        id: product.id,
        payload: {
          marketplace_published: true,
          marketplace_price: typeof price === "number" && price > 0 ? price : null,
        },
      });
      notifications.show({
        color: "green",
        message: t("marketplace.publish.listed"),
      });
      handleClose();
    } catch (err) {
      showError(err);
    }
  };

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={<Text fw={600}>{t("marketplace.publish.modal_title")}</Text>}
      size="sm"
      centered
    >
      <Stack gap="md">
        <Text size="sm">
          {t("marketplace.publish.modal_product")}: <strong>{productName}</strong>
        </Text>

        <NumberInput
          label={t("marketplace.publish.price_label")}
          placeholder={t("marketplace.publish.price_placeholder")}
          description={t("marketplace.publish.price_hint")}
          value={price}
          onChange={setPrice}
          min={0}
          step={100}
          thousandSeparator=" "
        />

        <Group justify="flex-end">
          <Button
            variant="subtle"
            onClick={handleClose}
            disabled={toggleMarketplace.isPending}
          >
            {t("common.cancel")}
          </Button>
          <Button
            onClick={() => { void handleSubmit(); }}
            loading={toggleMarketplace.isPending}
          >
            {t("marketplace.publish.publish_btn")}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
