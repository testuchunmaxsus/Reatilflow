/**
 * IncomingOrdersPage — kiruvchi marketplace buyurtmalar.
 *
 * Supplier (ta'minotchi) korxona uchun:
 * - Xaridor do'kondan kelgan buyurtmalar jadval
 * - Tasdiqlash / Rad etish tugmalari
 * - Tasdiqlangach kuryer tayinlash (GET /users?role=courier)
 * - Holat bo'yicha filter
 * - i18n uz/ru
 */

import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Group,
  Loader,
  Modal,
  Pagination,
  Select,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import {
  IconCheck,
  IconTruck,
  IconX,
} from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Can } from "@/rbac/Can";
import { useApiError } from "@/hooks/useApiError";
import {
  useIncomingOrders,
  useConfirmOrder,
  useShipOrder,
  useCouriers,
} from "./api/marketplaceApi";
import { RejectOrderModal } from "./components/RejectOrderModal";
import type { IncomingOrder } from "./types";

const PAGE_SIZE = 20;

// ─── Holat badge ─────────────────────────────────────────────────────────────

function OrderStatusBadge({ status }: { status: string }) {
  const { t } = useTranslation();
  const colorMap: Record<string, string> = {
    pending: "yellow",
    confirmed: "blue",
    rejected: "red",
    delivering: "teal",
    delivered: "green",
    accepted: "green",
  };
  return (
    <Badge color={colorMap[status] ?? "gray"} variant="light" size="sm">
      {t(`marketplace.order_status.${status}`, { defaultValue: status })}
    </Badge>
  );
}

// ─── Kuryer tayinlash modal ──────────────────────────────────────────────────

interface AssignCourierModalProps {
  opened: boolean;
  onClose: () => void;
  order: IncomingOrder | null;
}

function AssignCourierModal({
  opened,
  onClose,
  order,
}: AssignCourierModalProps) {
  const { t } = useTranslation();
  const { showError } = useApiError();
  const [courierId, setCourierId] = useState<string | null>(null);
  const { data: couriersData } = useCouriers();
  const shipOrder = useShipOrder();

  const courierOptions =
    couriersData?.items.map((c) => ({
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
      await shipOrder.mutateAsync({ id: order.id, courier_id: courierId });
      notifications.show({
        color: "teal",
        message: t("marketplace.messages.order_shipped"),
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
      title={<Text fw={600}>{t("marketplace.assign_courier.title")}</Text>}
      size="sm"
      centered
    >
      <Stack gap="md">
        <Select
          label={t("marketplace.assign_courier.courier_label")}
          placeholder={t("marketplace.assign_courier.courier_placeholder")}
          data={courierOptions}
          value={courierId}
          onChange={setCourierId}
          searchable
          required
        />
        <Group justify="flex-end">
          <Button variant="subtle" onClick={handleClose} disabled={shipOrder.isPending}>
            {t("common.cancel")}
          </Button>
          <Button
            onClick={() => { void handleSubmit(); }}
            disabled={!courierId}
            loading={shipOrder.isPending}
          >
            {t("marketplace.assign_courier.submit")}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

// ─── Asosiy komponent ────────────────────────────────────────────────────────

export function IncomingOrdersPage() {
  const { t } = useTranslation();
  const { showError } = useApiError();

  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const offset = (page - 1) * PAGE_SIZE;

  const [shipModalOpened, { open: openShipModal, close: closeShipModal }] =
    useDisclosure(false);
  const [rejectModalOpened, { open: openRejectModal, close: closeRejectModal }] =
    useDisclosure(false);
  const [selectedOrder, setSelectedOrder] = useState<IncomingOrder | null>(null);
  const [rejectingOrder, setRejectingOrder] = useState<IncomingOrder | null>(null);

  const { data, isLoading, isError, error } = useIncomingOrders({
    status: statusFilter || undefined,
    limit: PAGE_SIZE,
    offset,
  });

  const confirmOrder = useConfirmOrder();

  const handleConfirm = async (order: IncomingOrder) => {
    try {
      await confirmOrder.mutateAsync(order.id);
      notifications.show({
        color: "green",
        message: t("marketplace.messages.order_confirmed"),
      });
    } catch (err) {
      showError(err);
    }
  };

  const handleRejectClick = (order: IncomingOrder) => {
    setRejectingOrder(order);
    openRejectModal();
  };

  const handleShipClick = (order: IncomingOrder) => {
    setSelectedOrder(order);
    openShipModal();
  };

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1;

  const statusOptions = [
    { value: "", label: t("marketplace.filter.all_statuses") },
    { value: "pending", label: t("marketplace.order_status.pending") },
    { value: "confirmed", label: t("marketplace.order_status.confirmed") },
    { value: "rejected", label: t("marketplace.order_status.rejected") },
    { value: "delivering", label: t("marketplace.order_status.delivering") },
    { value: "delivered", label: t("marketplace.order_status.delivered") },
    { value: "accepted", label: t("marketplace.order_status.accepted") },
  ];

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Title order={3}>{t("marketplace.incoming.title")}</Title>
      </Group>

      {/* Filtr */}
      <Group gap="sm">
        <Select
          data={statusOptions}
          value={statusFilter}
          onChange={(v) => {
            setStatusFilter(v ?? "");
            setPage(1);
          }}
          w={200}
          aria-label={t("marketplace.filter.all_statuses")}
          allowDeselect={false}
        />
      </Group>

      {/* Jadval */}
      {isLoading ? (
        <Group justify="center" py="xl">
          <Loader />
          <Text c="dimmed">{t("common.loading")}</Text>
        </Group>
      ) : isError ? (
        <Box py="xl" ta="center">
          <Text c="red">
            {error instanceof Error ? error.message : t("errors.unknown")}
          </Text>
        </Box>
      ) : !data?.items.length ? (
        <Box py="xl" ta="center">
          <Text c="dimmed">{t("marketplace.incoming.empty")}</Text>
        </Box>
      ) : (
        <Table.ScrollContainer minWidth={900}>
          <Table striped highlightOnHover withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t("marketplace.table.buyer_store")}</Table.Th>
                <Table.Th>{t("marketplace.table.products")}</Table.Th>
                <Table.Th>{t("marketplace.table.total_amount")}</Table.Th>
                <Table.Th>{t("marketplace.table.status")}</Table.Th>
                <Table.Th>{t("marketplace.table.courier")}</Table.Th>
                <Table.Th>{t("marketplace.table.created_at")}</Table.Th>
                <Table.Th>{t("catalog.table.actions")}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.items.map((order) => (
                <Table.Tr key={order.id}>
                  <Table.Td>
                    <Text size="sm" fw={500}>
                      {order.buyer_store_name ?? "—"}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed">
                      {order.lines.length}{" "}
                      {t("marketplace.table.items_count")}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" ff="monospace">
                      {order.total_amount.toLocaleString()} UZS
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <OrderStatusBadge status={order.status} />
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed">
                      {order.courier_name ?? "—"}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed">
                      {new Date(order.created_at).toLocaleDateString()}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Can permission="catalog:edit">
                      <Group gap={4}>
                        {order.status === "pending" && (
                          <>
                            <Tooltip label={t("marketplace.actions.confirm")}>
                              <ActionIcon
                                variant="subtle"
                                color="green"
                                onClick={() => { void handleConfirm(order); }}
                                loading={confirmOrder.isPending}
                                aria-label={t("marketplace.actions.confirm")}
                              >
                                <IconCheck size={16} />
                              </ActionIcon>
                            </Tooltip>
                            <Tooltip label={t("marketplace.actions.reject")}>
                              <ActionIcon
                                variant="subtle"
                                color="red"
                                onClick={() => handleRejectClick(order)}
                                aria-label={t("marketplace.actions.reject")}
                              >
                                <IconX size={16} />
                              </ActionIcon>
                            </Tooltip>
                          </>
                        )}
                        {order.status === "confirmed" && (
                          <Tooltip label={t("marketplace.actions.ship")}>
                            <ActionIcon
                              variant="subtle"
                              color="teal"
                              onClick={() => handleShipClick(order)}
                              aria-label={t("marketplace.actions.ship")}
                            >
                              <IconTruck size={16} />
                            </ActionIcon>
                          </Tooltip>
                        )}
                      </Group>
                    </Can>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}

      {totalPages > 1 && (
        <Group justify="center">
          <Pagination value={page} onChange={setPage} total={totalPages} size="sm" />
        </Group>
      )}

      <AssignCourierModal
        opened={shipModalOpened}
        onClose={closeShipModal}
        order={selectedOrder}
      />

      <RejectOrderModal
        opened={rejectModalOpened}
        onClose={closeRejectModal}
        order={rejectingOrder}
      />
    </Stack>
  );
}
