/**
 * OutgoingOrdersPage — chiquvchi marketplace buyurtmalar.
 *
 * Xaridor sifatida: o'z do'konlaridan berilgan buyurtmalar holati kuzatish.
 * - Supplier nomi, mahsulotlar, summa, holat
 * - Holat bo'yicha filter
 * - "delivered" holat uchun "Qabul qilish" tugmasi + AcceptOrderModal
 * - i18n uz/ru
 */

import {
  ActionIcon,
  Badge,
  Box,
  Group,
  Loader,
  Pagination,
  Select,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { IconCheckbox } from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Can } from "@/rbac/Can";
import { useOutgoingOrders } from "./api/marketplaceApi";
import { AcceptOrderModal } from "./components/AcceptOrderModal";
import type { OutgoingOrder } from "./types";

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

// ─── Asosiy komponent ────────────────────────────────────────────────────────

export function OutgoingOrdersPage() {
  const { t } = useTranslation();

  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const offset = (page - 1) * PAGE_SIZE;

  const [acceptModalOpened, { open: openAcceptModal, close: closeAcceptModal }] =
    useDisclosure(false);
  const [selectedOrder, setSelectedOrder] = useState<OutgoingOrder | null>(null);

  const handleAcceptClick = (order: OutgoingOrder) => {
    setSelectedOrder(order);
    openAcceptModal();
  };

  const { data, isLoading, isError, error } = useOutgoingOrders({
    status: statusFilter || undefined,
    limit: PAGE_SIZE,
    offset,
  });

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
        <Title order={3}>{t("marketplace.outgoing.title")}</Title>
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
          <Text c="dimmed">{t("marketplace.outgoing.empty")}</Text>
        </Box>
      ) : (
        <Table.ScrollContainer minWidth={860}>
          <Table striped highlightOnHover withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t("marketplace.table.supplier")}</Table.Th>
                <Table.Th>{t("marketplace.table.products")}</Table.Th>
                <Table.Th>{t("marketplace.table.total_amount")}</Table.Th>
                <Table.Th>{t("marketplace.table.status")}</Table.Th>
                <Table.Th>{t("marketplace.table.created_at")}</Table.Th>
                <Table.Th>{t("catalog.table.actions")}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.items.map((order) => (
                <Table.Tr key={order.id}>
                  <Table.Td>
                    <Text size="sm" fw={500}>
                      {order.supplier_name ?? "—"}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed">
                      {order.lines.length} {t("marketplace.table.items_count")}
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
                      {new Date(order.created_at).toLocaleDateString()}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Can permission="catalog:edit">
                      {order.status === "delivered" && (
                        <Tooltip
                          label={t("marketplace.actions.accept", {
                            defaultValue: "Qabul qilish",
                          })}
                        >
                          <ActionIcon
                            variant="subtle"
                            color="green"
                            onClick={() => handleAcceptClick(order)}
                            aria-label={t("marketplace.actions.accept", {
                              defaultValue: "Qabul qilish",
                            })}
                          >
                            <IconCheckbox size={16} />
                          </ActionIcon>
                        </Tooltip>
                      )}
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

      <AcceptOrderModal
        opened={acceptModalOpened}
        onClose={closeAcceptModal}
        order={selectedOrder}
      />
    </Stack>
  );
}
