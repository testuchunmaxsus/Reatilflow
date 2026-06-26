/**
 * RejectOrderModal — buyurtmani rad etish modali.
 *
 * Supplier (ta'minotchi) sifatida pending buyurtmani rad etish.
 *   PATCH /marketplace/orders/{id}/reject  { reason?: string }
 *
 * reason ixtiyoriy, max 500 belgi.
 */

import {
  Button,
  Group,
  Modal,
  Stack,
  Text,
  Textarea,
} from "@mantine/core";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { notifications } from "@mantine/notifications";
import { useApiError } from "@/hooks/useApiError";
import { useRejectOrder } from "../api/marketplaceApi";
import type { IncomingOrder } from "../types";

const MAX_REASON_LENGTH = 500;

interface RejectOrderModalProps {
  opened: boolean;
  onClose: () => void;
  order: IncomingOrder | null;
}

export function RejectOrderModal({
  opened,
  onClose,
  order,
}: RejectOrderModalProps) {
  const { t } = useTranslation();
  const { showError } = useApiError();
  const rejectOrder = useRejectOrder();
  const [reason, setReason] = useState("");

  const handleClose = () => {
    setReason("");
    onClose();
  };

  const handleSubmit = async () => {
    if (!order) return;
    try {
      await rejectOrder.mutateAsync({
        id: order.id,
        payload: reason.trim() ? { reason: reason.trim() } : undefined,
      });
      notifications.show({
        color: "red",
        message: t("marketplace.messages.order_rejected"),
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
      title={
        <Text fw={600}>
          {t("marketplace.reject.modal_title", { defaultValue: "Buyurtmani rad etish" })}
        </Text>
      }
      size="sm"
      centered
    >
      <Stack gap="md">
        {order && (
          <Text size="sm" c="dimmed">
            {t("marketplace.table.buyer_store")}:{" "}
            <Text component="span" size="sm" fw={500} c="dark">
              {order.buyer_store_name ?? "—"}
            </Text>
          </Text>
        )}

        <Textarea
          label={t("marketplace.reject.reason_label", {
            defaultValue: "Sabab (ixtiyoriy)",
          })}
          placeholder={t("marketplace.reject.reason_placeholder", {
            defaultValue: "Rad etish sababini kiriting...",
          })}
          description={t("marketplace.reject.reason_hint", {
            defaultValue: "Maksimal 500 belgi",
          })}
          value={reason}
          onChange={(e) => setReason(e.currentTarget.value.slice(0, MAX_REASON_LENGTH))}
          autosize
          minRows={3}
          maxRows={6}
          rightSection={
            <Text size="xs" c="dimmed" pr={4}>
              {reason.length}/{MAX_REASON_LENGTH}
            </Text>
          }
          rightSectionWidth={60}
        />

        <Group justify="flex-end">
          <Button
            variant="subtle"
            onClick={handleClose}
            disabled={rejectOrder.isPending}
          >
            {t("common.cancel")}
          </Button>
          <Button
            color="red"
            onClick={() => {
              void handleSubmit();
            }}
            loading={rejectOrder.isPending}
          >
            {t("marketplace.actions.reject")}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
