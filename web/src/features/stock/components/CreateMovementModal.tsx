/**
 * CreateMovementModal — yangi ombor harakatini qayd etish modali.
 *
 * Faqat administrator (stock:create ruxsati bilan) ko'rinadi.
 * Backend: POST /stock/movements (APPEND-ONLY ledger, idempotentlik uchun client_uuid).
 *
 * Maydonlar:
 *   - product_id    (UUID, majburiy)
 *   - warehouse_id  (UUID, majburiy)
 *   - type          (in | out | transfer | adjust)
 *   - qty           (musbat son)
 *   - ref_type      (ixtiyoriy)
 */

import {
  Button,
  Group,
  Modal,
  NumberInput,
  Select,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useCreateStockMovement } from "../api/stockApi";
import type { MovementType, StockMovementCreate } from "../types";

// ─── Harakat turi options ────────────────────────────────────────────────────

const MOVEMENT_TYPE_OPTIONS: { value: MovementType; labelKey: string }[] = [
  { value: "in", labelKey: "stock.movement_form.type_in" },
  { value: "out", labelKey: "stock.movement_form.type_out" },
  { value: "transfer", labelKey: "stock.movement_form.type_transfer" },
  { value: "adjust", labelKey: "stock.movement_form.type_adjust" },
];

// ─── Props ───────────────────────────────────────────────────────────────────

interface CreateMovementModalProps {
  opened: boolean;
  onClose: () => void;
}

// ─── Komponent ───────────────────────────────────────────────────────────────

export function CreateMovementModal({
  opened,
  onClose,
}: CreateMovementModalProps) {
  const { t } = useTranslation();
  const { mutateAsync, isPending } = useCreateStockMovement();

  // Forma holati
  const [productId, setProductId] = useState("");
  const [warehouseId, setWarehouseId] = useState("");
  const [movementType, setMovementType] = useState<MovementType>("in");
  const [qty, setQty] = useState<number | string>("");
  const [refType, setRefType] = useState("");

  // Validatsiya xatolari
  const [errors, setErrors] = useState<Record<string, string>>({});

  function validate(): boolean {
    const errs: Record<string, string> = {};
    const uuidRegex =
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

    if (!productId.trim()) {
      errs.product_id = t("stock.movement_form.product_id_required", {
        defaultValue: "Mahsulot ID majburiy",
      });
    } else if (!uuidRegex.test(productId.trim())) {
      errs.product_id = t("stock.movement_form.product_id_invalid", {
        defaultValue: "UUID formatida kiriting",
      });
    }
    if (!warehouseId.trim()) {
      errs.warehouse_id = t("stock.movement_form.warehouse_id_required", {
        defaultValue: "Ombor ID majburiy",
      });
    } else if (!uuidRegex.test(warehouseId.trim())) {
      errs.warehouse_id = t("stock.movement_form.warehouse_id_invalid", {
        defaultValue: "UUID formatida kiriting",
      });
    }
    const qtyNum = Number(qty);
    if (!qty || isNaN(qtyNum) || qtyNum <= 0) {
      errs.qty = t("stock.movement_form.qty_positive", {
        defaultValue: "Miqdor 0 dan katta bo'lishi kerak",
      });
    }

    setErrors(errs);
    return Object.keys(errs).length === 0;
  }

  function resetForm() {
    setProductId("");
    setWarehouseId("");
    setMovementType("in");
    setQty("");
    setRefType("");
    setErrors({});
  }

  async function handleSubmit() {
    if (!validate()) return;

    const payload: StockMovementCreate = {
      product_id: productId.trim(),
      warehouse_id: warehouseId.trim(),
      type: movementType,
      qty: String(qty),
      ref_type: refType.trim() || null,
    };

    try {
      await mutateAsync(payload);
      notifications.show({
        color: "green",
        message: t("stock.messages.movement_created", {
          defaultValue: "Harakat muvaffaqiyatli qayd etildi",
        }),
      });
      resetForm();
      onClose();
    } catch (err) {
      notifications.show({
        color: "red",
        message:
          err instanceof Error
            ? err.message
            : t("errors.unknown", { defaultValue: "Xato yuz berdi" }),
      });
    }
  }

  function handleClose() {
    resetForm();
    onClose();
  }

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={t("stock.movement_form.title", {
        defaultValue: "Yangi ombor harakati",
      })}
      size="md"
    >
      <Stack gap="sm">
        {/* Mahsulot ID */}
        <TextInput
          label={t("stock.movement_form.product_id", {
            defaultValue: "Mahsulot ID (UUID)",
          })}
          placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
          value={productId}
          onChange={(e) => setProductId(e.currentTarget.value)}
          error={errors.product_id}
          required
        />

        {/* Ombor ID */}
        <TextInput
          label={t("stock.movement_form.warehouse_id", {
            defaultValue: "Ombor ID (UUID)",
          })}
          placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
          value={warehouseId}
          onChange={(e) => setWarehouseId(e.currentTarget.value)}
          error={errors.warehouse_id}
          required
        />

        {/* Harakat turi */}
        <Select
          label={t("stock.movement_form.movement_type", {
            defaultValue: "Harakat turi",
          })}
          data={MOVEMENT_TYPE_OPTIONS.map((o) => ({
            value: o.value,
            label: t(o.labelKey, { defaultValue: o.value }),
          }))}
          value={movementType}
          onChange={(v) => setMovementType((v as MovementType) ?? "in")}
          allowDeselect={false}
          required
        />

        {/* Miqdor */}
        <NumberInput
          label={t("stock.movement_form.qty", { defaultValue: "Miqdor" })}
          placeholder="1"
          value={qty}
          onChange={setQty}
          min={0.001}
          decimalScale={3}
          error={errors.qty}
          required
        />

        {/* Havola turi (ixtiyoriy) */}
        <TextInput
          label={t("stock.movement_form.ref_type", {
            defaultValue: "Havola turi (ixtiyoriy)",
          })}
          placeholder={t("stock.movement_form.ref_type_placeholder", {
            defaultValue: "Masalan: order, purchase...",
          })}
          value={refType}
          onChange={(e) => setRefType(e.currentTarget.value)}
        />

        {/* adjust haqida eslatma */}
        {movementType === "adjust" && (
          <Text size="xs" c="dimmed">
            {t("stock.movement_form.adjust_note", {
              defaultValue:
                "adjust — qoldiqni OSHIRADI (delta += qty). Kamaytirish uchun 'out' turini ishlating.",
            })}
          </Text>
        )}

        {/* Tugmalar */}
        <Group justify="flex-end" mt="xs">
          <Button variant="default" onClick={handleClose} disabled={isPending}>
            {t("common.cancel", { defaultValue: "Bekor qilish" })}
          </Button>
          <Button onClick={handleSubmit} loading={isPending}>
            {t("stock.movement_form.submit", { defaultValue: "Qayd etish" })}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
