/**
 * CreateMarketplaceOrderModal — marketplace buyurtma berish modali.
 *
 * Tanlangan mahsulot(lar) bo'yicha POST /marketplace/orders so'rovi.
 *
 * XATO holatlari:
 *   409 marketplace.contract_required → aniq xabar:
 *     "Bu korxona bilan shartnoma yo'q — agent orqali buyurtma bering"
 *   Boshqa xatolar → useApiError orqali.
 *
 * Muvaffaqiyat → yashil notification + modal yopiladi.
 */

import {
  Button,
  Divider,
  Group,
  Modal,
  NumberInput,
  Stack,
  Text,
  Alert,
  ThemeIcon,
  Box,
} from "@mantine/core";
import { IconPackage, IconAlertCircle } from "@tabler/icons-react";
import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { notifications } from "@mantine/notifications";
import { ApiError } from "@/api/client";
import { useApiError } from "@/hooks/useApiError";
import { useCreateMarketplaceOrder } from "../api/marketplaceApi";
import type { MarketplaceProductOut } from "../types";

// ─── Tipler ───────────────────────────────────────────────────────────────────

export interface OrderLineItem {
  product: MarketplaceProductOut;
  qty: number;
}

interface CreateMarketplaceOrderModalProps {
  opened: boolean;
  onClose: () => void;
  /** Buyurtma beriladigan mahsulotlar (bir xil supplierdan) */
  items: OrderLineItem[];
  /** Ixtiyoriy: buyer do'kon UUID (store roli uchun avtomatik) */
  buyerStoreId?: string | null;
}

// ─── Modal ────────────────────────────────────────────────────────────────────

export function CreateMarketplaceOrderModal({
  opened,
  onClose,
  items,
  buyerStoreId,
}: CreateMarketplaceOrderModalProps) {
  const { t } = useTranslation();
  const { showError } = useApiError();
  const createOrder = useCreateMarketplaceOrder();

  // Har bir mahsulot uchun miqdor holati
  const [quantities, setQuantities] = useState<Record<string, number | string>>({});
  // 409 shartnoma-gate xatosi uchun
  const [contractError, setContractError] = useState(false);

  // Modal ochilganda holatni tiklash
  useEffect(() => {
    if (opened) {
      setContractError(false);
      setQuantities(
        Object.fromEntries(items.map((item) => [item.product.id, item.qty || 1])),
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened]);

  const handleClose = () => {
    setContractError(false);
    setQuantities({});
    onClose();
  };

  // Umumiy summa hisobi
  const totalAmount = items.reduce((sum, item) => {
    const qty = typeof quantities[item.product.id] === "number"
      ? (quantities[item.product.id] as number)
      : Number(quantities[item.product.id]) || 0;
    const price = item.product.price ?? item.product.marketplace_price ?? 0;
    return sum + price * qty;
  }, 0);

  const allValid = items.every((item) => {
    const qty = quantities[item.product.id];
    const num = typeof qty === "number" ? qty : Number(qty);
    return !isNaN(num) && num > 0;
  });

  const handleSubmit = async () => {
    if (!allValid || items.length === 0) return;
    setContractError(false);

    const lines = items.map((item) => ({
      product_id: item.product.id,
      qty: typeof quantities[item.product.id] === "number"
        ? (quantities[item.product.id] as number)
        : Number(quantities[item.product.id]),
    }));

    try {
      await createOrder.mutateAsync({
        lines,
        buyer_store_id: buyerStoreId ?? null,
      });
      notifications.show({
        color: "green",
        message: t("marketplace.browse.order_success", {
          defaultValue: "Buyurtma muvaffaqiyatli berildi!",
        }),
        autoClose: 3000,
      });
      handleClose();
    } catch (err) {
      // 409 marketplace.contract_required — maxsus UI
      if (
        err instanceof ApiError &&
        err.status === 409 &&
        err.envelope.message_key === "marketplace.contract_required"
      ) {
        setContractError(true);
        return;
      }
      showError(err);
    }
  };

  // Supplier nomi (birinchi mahsulotdan)
  const supplierName = items[0]?.product.supplier_name ?? "—";

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={
        <Text fw={600}>
          {t("marketplace.browse.order_modal_title", {
            defaultValue: "Buyurtma berish",
          })}
        </Text>
      }
      size="md"
      centered
    >
      <Stack gap="md">
        {/* Supplier */}
        <Text size="sm" c="dimmed">
          {t("marketplace.table.supplier", { defaultValue: "Supplier" })}:{" "}
          <Text component="span" size="sm" fw={500} c="dark">
            {supplierName}
          </Text>
        </Text>

        <Divider />

        {/* Mahsulotlar ro'yxati */}
        {items.map((item) => {
          const qty = quantities[item.product.id];
          const qtyNum = typeof qty === "number" ? qty : Number(qty);
          const price = item.product.price ?? item.product.marketplace_price ?? 0;
          const lineTotal = price * (isNaN(qtyNum) ? 0 : qtyNum);

          return (
            <Box key={item.product.id}>
              <Group gap="xs" mb="xs">
                <ThemeIcon size="sm" variant="light" color="blue">
                  <IconPackage size={12} />
                </ThemeIcon>
                <Text size="sm" fw={600} style={{ flex: 1 }}>
                  {item.product.name || item.product.name_uz}
                </Text>
                {item.product.sku && (
                  <Text size="xs" c="dimmed">
                    {item.product.sku}
                  </Text>
                )}
              </Group>

              <Group gap="sm" pl="xl" align="flex-end">
                <NumberInput
                  label={t("marketplace.browse.qty_label", {
                    defaultValue: "Miqdor",
                  })}
                  value={qty}
                  onChange={(v) =>
                    setQuantities((prev) => ({ ...prev, [item.product.id]: v }))
                  }
                  min={1}
                  step={1}
                  decimalScale={2}
                  required
                  size="sm"
                  w={120}
                  suffix={` ${item.product.unit}`}
                />
                <Text size="xs" c="dimmed" mb={6}>
                  {price.toLocaleString()} UZS ×{" "}
                  {isNaN(qtyNum) ? 0 : qtyNum} ={" "}
                  <Text component="span" size="xs" fw={600} c="dark">
                    {lineTotal.toLocaleString()} UZS
                  </Text>
                </Text>
              </Group>
            </Box>
          );
        })}

        <Divider />

        {/* Umumiy summa */}
        <Group justify="flex-end">
          <Text size="sm" c="dimmed">
            {t("marketplace.table.total_amount", { defaultValue: "Jami" })}:
          </Text>
          <Text size="sm" fw={700} ff="monospace">
            {totalAmount.toLocaleString()} UZS
          </Text>
        </Group>

        {/* 409 shartnoma-gate xabari */}
        {contractError && (
          <Alert
            color="orange"
            icon={<IconAlertCircle size={16} />}
            title={t("marketplace.browse.contract_required_title", {
              defaultValue: "Shartnoma talab qilinadi",
            })}
          >
            {t("marketplace.browse.contract_required_message", {
              defaultValue:
                "Bu korxona bilan shartnoma yo'q — agent orqali buyurtma bering.",
            })}
          </Alert>
        )}

        {/* Tugmalar */}
        <Group justify="flex-end">
          <Button
            variant="subtle"
            onClick={handleClose}
            disabled={createOrder.isPending}
          >
            {t("common.cancel")}
          </Button>
          <Button
            onClick={() => {
              void handleSubmit();
            }}
            disabled={!allValid || items.length === 0}
            loading={createOrder.isPending}
          >
            {t("marketplace.browse.submit_order", {
              defaultValue: "Buyurtma berish",
            })}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
