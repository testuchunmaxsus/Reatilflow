/**
 * AssignCourierModal — oddiy buyurtmaga kuryer tayinlash modali.
 *
 * Props:
 *   opened   — modal ochiq/yopiq holati
 *   onClose  — yopish callback
 *   order    — tayinlanayotgan buyurtma (null bo'lsa modal inert)
 *
 * Oqim:
 *   1. useCouriers() → kuryer dropdown
 *   2. useAssignCourier().mutateAsync({ order_id, courier_id })
 *   3. Muvaffaqiyatda: yashil notification + onClose
 *   4. Xatoda: useApiError().showError(err)
 */

import {
  Button,
  Group,
  Modal,
  Select,
  Stack,
  Text,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useApiError } from "@/hooks/useApiError";
import { useCouriers } from "@/features/marketplace/api/marketplaceApi";
import { useAssignCourier } from "../api/deliveryApi";
import type { OrderOut } from "@/features/orders/types";

interface AssignCourierModalProps {
  opened: boolean;
  onClose: () => void;
  order: OrderOut | null;
}

export function AssignCourierModal({
  opened,
  onClose,
  order,
}: AssignCourierModalProps) {
  const { t } = useTranslation();
  const { showError } = useApiError();
  const [courierId, setCourierId] = useState<string | null>(null);

  const { data: couriersData } = useCouriers();
  const assignCourier = useAssignCourier();

  const courierOptions =
    couriersData?.items?.map((c) => ({
      value: c.id,
      label: c.full_name,
    })) ?? [];

  const handleClose = () => {
    setCourierId(null);
    onClose();
  };

  const handleSubmit = async () => {
    if (!order || !courierId) return;
    try {
      await assignCourier.mutateAsync({
        order_id: order.id,
        courier_id: courierId,
      });
      notifications.show({
        color: "green",
        message: t("delivery.assign_courier.success", {
          defaultValue: "Kuryer tayinlandi",
        }),
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
          {t("delivery.assign_courier.title", {
            defaultValue: "Kuryer tayinlash",
          })}
        </Text>
      }
      size="sm"
      centered
    >
      <Stack gap="md">
        <Select
          label={t("delivery.assign_courier.courier_label", {
            defaultValue: "Kuryer",
          })}
          placeholder={t("delivery.assign_courier.placeholder", {
            defaultValue: "Kuryerni tanlang",
          })}
          data={courierOptions}
          value={courierId}
          onChange={setCourierId}
          searchable
          required
        />
        <Group justify="flex-end">
          <Button
            variant="subtle"
            onClick={handleClose}
            disabled={assignCourier.isPending}
          >
            {t("common.cancel")}
          </Button>
          <Button
            onClick={() => {
              void handleSubmit();
            }}
            disabled={!courierId}
            loading={assignCourier.isPending}
          >
            {t("delivery.assign_courier.submit", {
              defaultValue: "Tayinlash",
            })}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
