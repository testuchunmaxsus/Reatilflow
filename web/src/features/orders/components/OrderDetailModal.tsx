/**
 * OrderDetailModal — buyurtma tafsilotlari va holat o'zgartirish modali.
 *
 * Xususiyatlar:
 * - Buyurtma qatorlari (mahsulot, qty, narx, line_total)
 * - Jami summa
 * - Holat o'zgartirish tugmalari (VALID_TRANSITIONS bo'yicha)
 * - RBAC: faqat <Can permission="orders:edit"> holat tugmalari ko'rinadi
 * - Server-avtoritar: noqonuniy o'tish 422 → notification
 * - i18n uz/ru
 */

import {
  Badge,
  Box,
  Button,
  Divider,
  Group,
  Loader,
  Modal,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { useTranslation } from "react-i18next";
import { notifications } from "@mantine/notifications";
import { Can } from "@/rbac/Can";
import { useApiError } from "@/hooks/useApiError";
import { useOrder, useUpdateOrderStatus } from "../api/ordersApi";
import { OrderStatusBadge } from "./OrderStatusBadge";
import { VALID_TRANSITIONS } from "../types";
import type { OrderStatus } from "../types";

interface OrderDetailModalProps {
  opened: boolean;
  onClose: () => void;
  orderId: string | null;
}

export function OrderDetailModal({
  opened,
  onClose,
  orderId,
}: OrderDetailModalProps) {
  const { t } = useTranslation();
  const { showError } = useApiError();

  const { data: order, isLoading } = useOrder(orderId ?? "", opened && Boolean(orderId));
  const updateStatus = useUpdateOrderStatus();

  const handleStatusChange = async (toStatus: OrderStatus) => {
    if (!order) return;
    try {
      await updateStatus.mutateAsync({
        id: order.id,
        data: { status: toStatus, version: order.version },
      });
      notifications.show({
        color: "green",
        message: t("orders.messages.status_updated", {
          status: t(`orders.status.${toStatus}`),
        }),
      });
    } catch (err) {
      showError(err);
    }
  };

  const validNextStatuses: OrderStatus[] = order
    ? VALID_TRANSITIONS[order.status]
    : [];

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={
        <Group gap="sm">
          <Title order={5}>{t("orders.detail.title")}</Title>
          {order && <OrderStatusBadge status={order.status} />}
        </Group>
      }
      size="xl"
      centered
    >
      {isLoading ? (
        <Group justify="center" py="xl">
          <Loader size="sm" />
          <Text c="dimmed">{t("common.loading")}</Text>
        </Group>
      ) : !order ? (
        <Box py="xl" ta="center">
          <Text c="dimmed">{t("orders.detail.not_found")}</Text>
        </Box>
      ) : (
        <Stack gap="md">
          {/* Meta ma'lumotlar */}
          <Group gap="xl" wrap="wrap">
            <Box>
              <Text size="xs" c="dimmed">{t("orders.table.number")}</Text>
              <Text size="sm" fw={500} ff="monospace">
                {order.id.slice(0, 8).toUpperCase()}
              </Text>
            </Box>
            <Box>
              <Text size="xs" c="dimmed">{t("orders.table.date")}</Text>
              <Text size="sm">
                {new Date(order.ordered_at).toLocaleString()}
              </Text>
            </Box>
            <Box>
              <Text size="xs" c="dimmed">{t("orders.table.store")}</Text>
              <Text size="sm" ff="monospace">
                {order.store_id.slice(0, 8)}...
              </Text>
            </Box>
            <Box>
              <Text size="xs" c="dimmed">{t("orders.table.mode")}</Text>
              <Badge variant="outline" size="sm">
                {order.mode}
              </Badge>
            </Box>
          </Group>

          <Divider />

          {/* Buyurtma qatorlari */}
          <Text fw={600} size="sm">
            {t("orders.detail.lines")}
          </Text>
          <Table.ScrollContainer minWidth={500}>
            <Table striped withTableBorder>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t("orders.detail.product_id")}</Table.Th>
                  <Table.Th ta="right">{t("orders.detail.qty")}</Table.Th>
                  <Table.Th ta="right">{t("orders.detail.unit_price")}</Table.Th>
                  <Table.Th ta="right">{t("orders.detail.discount")}</Table.Th>
                  <Table.Th ta="right">{t("orders.detail.line_total")}</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {order.lines.map((line) => (
                  <Table.Tr key={line.id}>
                    <Table.Td>
                      <Text size="sm" ff="monospace">
                        {line.product_id.slice(0, 8)}...
                      </Text>
                    </Table.Td>
                    <Table.Td ta="right">
                      <Text size="sm">{line.qty}</Text>
                    </Table.Td>
                    <Table.Td ta="right">
                      <Text size="sm">
                        {Number(line.unit_price).toLocaleString()} {order.currency}
                      </Text>
                    </Table.Td>
                    <Table.Td ta="right">
                      <Text size="sm" c={Number(line.discount) > 0 ? "green" : "dimmed"}>
                        {Number(line.discount).toLocaleString()}
                      </Text>
                    </Table.Td>
                    <Table.Td ta="right">
                      <Text size="sm" fw={500}>
                        {Number(line.line_total).toLocaleString()} {order.currency}
                      </Text>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>

          {/* Jami */}
          <Group justify="flex-end">
            <Text fw={700} size="lg">
              {t("orders.detail.total")}: {Number(order.total_amount).toLocaleString()}{" "}
              {order.currency}
            </Text>
          </Group>

          <Divider />

          {/* Holat o'zgartirish tugmalari */}
          <Can permission="orders:edit">
            {validNextStatuses.length > 0 ? (
              <Group gap="sm">
                <Text size="sm" c="dimmed">
                  {t("orders.detail.change_status")}:
                </Text>
                {validNextStatuses.map((nextStatus) => (
                  <Button
                    key={nextStatus}
                    size="xs"
                    variant="light"
                    color={nextStatus === "canceled" ? "red" : "blue"}
                    loading={updateStatus.isPending}
                    onClick={() => { void handleStatusChange(nextStatus); }}
                    data-testid={`status-btn-${nextStatus}`}
                  >
                    → {t(`orders.status.${nextStatus}`)}
                  </Button>
                ))}
              </Group>
            ) : (
              <Text size="sm" c="dimmed">
                {t("orders.detail.terminal_status")}
              </Text>
            )}
          </Can>

          {/* Yopish */}
          <Group justify="flex-end">
            <Button variant="subtle" onClick={onClose}>
              {t("common.close")}
            </Button>
          </Group>
        </Stack>
      )}
    </Modal>
  );
}
