/**
 * AcceptOrderModal — yetkazilgan buyurtmani qabul qilish modali.
 *
 * Xaridor (buyer) korxona uchun:
 *   PATCH /marketplace/orders/{id}/accept
 *   Har line uchun: expiry_date (yaroqlilik muddati) + markup_percent (ustama %)
 *
 * Mobil naqshi: marketplace_accept_screen.dart
 */

import {
  Button,
  Group,
  Modal,
  NumberInput,
  Stack,
  Text,
  Divider,
  Box,
  ThemeIcon,
} from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { IconPackage } from "@tabler/icons-react";
import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { notifications } from "@mantine/notifications";
import { useApiError } from "@/hooks/useApiError";
import { useAcceptOrder } from "../api/marketplaceApi";
import type { OutgoingOrder, AcceptOrderLinePayload } from "../types";

// ─── Har bir line uchun forma holati ─────────────────────────────────────────

interface LineFormState {
  expiry_date: Date | null;
  markup_percent: number | string;
}

function emptyLineState(): LineFormState {
  return { expiry_date: null, markup_percent: "" };
}

function isLineValid(s: LineFormState): boolean {
  const markup = typeof s.markup_percent === "number" ? s.markup_percent : Number(s.markup_percent);
  return s.expiry_date !== null && !isNaN(markup) && markup >= 0;
}

// ─── Modal ────────────────────────────────────────────────────────────────────

interface AcceptOrderModalProps {
  opened: boolean;
  onClose: () => void;
  order: OutgoingOrder | null;
}

export function AcceptOrderModal({
  opened,
  onClose,
  order,
}: AcceptOrderModalProps) {
  const { t } = useTranslation();
  const { showError } = useApiError();
  const acceptOrder = useAcceptOrder();

  // line_id → form holati
  const [lineStates, setLineStates] = useState<Record<string, LineFormState>>({});

  // Modal ochilganda line holatlarini qayta initsializatsiya
  useEffect(() => {
    if (opened && order) {
      setLineStates(
        Object.fromEntries(order.lines.map((l) => [l.id, emptyLineState()])),
      );
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened, order?.id]);

  const states = order ? lineStates : {};

  const allValid =
    order !== null &&
    order.lines.length > 0 &&
    order.lines.every((l) => isLineValid(states[l.id] ?? emptyLineState()));

  const handleClose = () => {
    setLineStates({});
    onClose();
  };

  const handleSubmit = async () => {
    if (!order) return;
    const lines: AcceptOrderLinePayload[] = order.lines.map((l) => {
      const st = states[l.id] ?? emptyLineState();
      const markup = typeof st.markup_percent === "number"
        ? st.markup_percent
        : Number(st.markup_percent);
      // ISO YYYY-MM-DD
      const expiry = st.expiry_date!.toISOString().split("T")[0];
      return { line_id: l.id, expiry_date: expiry, markup_percent: markup };
    });
    try {
      await acceptOrder.mutateAsync({ id: order.id, payload: { lines } });
      notifications.show({
        color: "green",
        message: t("marketplace.messages.order_accepted", {
          defaultValue: "Buyurtma qabul qilindi! Mahsulotlar inventarga qo'shildi.",
        }),
      });
      handleClose();
    } catch (err) {
      showError(err);
    }
  };

  const setLineField = <K extends keyof LineFormState>(
    lineId: string,
    field: K,
    value: LineFormState[K],
  ) => {
    setLineStates((prev) => ({
      ...prev,
      [lineId]: { ...(prev[lineId] ?? emptyLineState()), [field]: value },
    }));
  };

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={
        <Text fw={600}>
          {t("marketplace.accept.modal_title", {
            defaultValue: "Buyurtmani qabul qilish",
          })}
        </Text>
      }
      size="md"
      centered
    >

      <Stack gap="md">
        {order && (
          <>
            {/* Buyurtma haqida xulosa */}
            <Text size="sm" c="dimmed">
              {t("marketplace.accept.supplier_label", { defaultValue: "Supplier" })}:{" "}
              <Text component="span" size="sm" fw={500} c="dark">
                {order.supplier_name ?? "—"}
              </Text>
            </Text>

            <Divider />

            {/* Har bir line uchun forma */}
            {order.lines.map((line) => {
              const st = states[line.id] ?? emptyLineState();
              const markup = typeof st.markup_percent === "number"
                ? st.markup_percent
                : Number(st.markup_percent);
              const markupError =
                st.markup_percent !== "" && (isNaN(markup) || markup < 0)
                  ? t("marketplace.accept.markup_error", { defaultValue: "0 dan katta raqam kiriting" })
                  : undefined;

              return (
                <Box key={line.id}>
                  <Group gap="xs" mb="xs">
                    <ThemeIcon size="sm" variant="light" color="blue">
                      <IconPackage size={12} />
                    </ThemeIcon>
                    <Text size="sm" fw={600}>
                      {line.product_name ?? "—"}
                    </Text>
                    <Text size="xs" c="dimmed">
                      × {line.qty}
                    </Text>
                  </Group>

                  <Stack gap="xs" pl="xl">
                    <DateInput
                      label={t("marketplace.accept.expiry_date_label", {
                        defaultValue: "Yaroqlilik muddati *",
                      })}
                      placeholder={t("marketplace.accept.expiry_date_placeholder", {
                        defaultValue: "Muddatni tanlang",
                      })}
                      value={st.expiry_date}
                      onChange={(v) => setLineField(line.id, "expiry_date", v)}
                      minDate={new Date()}
                      required
                      size="sm"
                    />
                    <NumberInput
                      label={t("marketplace.accept.markup_label", {
                        defaultValue: "Ustama foizi (%) *",
                      })}
                      placeholder={t("marketplace.accept.markup_placeholder", {
                        defaultValue: "Masalan: 15",
                      })}
                      suffix="%"
                      value={st.markup_percent}
                      onChange={(v) => setLineField(line.id, "markup_percent", v)}
                      min={0}
                      step={0.5}
                      decimalScale={2}
                      error={markupError}
                      required
                      size="sm"
                    />
                  </Stack>

                  <Divider mt="sm" />
                </Box>
              );
            })}

            <Group justify="flex-end">
              <Button
                variant="subtle"
                onClick={handleClose}
                disabled={acceptOrder.isPending}
              >
                {t("common.cancel")}
              </Button>
              <Button
                color="green"
                onClick={() => {
                  void handleSubmit();
                }}
                disabled={!allValid}
                loading={acceptOrder.isPending}
              >
                {t("marketplace.accept.submit_btn", { defaultValue: "Qabul qilish" })}
              </Button>
            </Group>
          </>
        )}
      </Stack>
    </Modal>
  );
}
