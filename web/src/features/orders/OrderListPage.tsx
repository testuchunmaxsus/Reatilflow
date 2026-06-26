/**
 * OrderListPage — buyurtmalar ro'yxati sahifasi.
 *
 * Xususiyatlar:
 * - Paginated jadval (buyurtma raqami/sana, do'kon, status[badge], summa)
 * - Filter: status, sana (from/to)
 * - TanStack Query
 * - RBAC: yaratish tugmasi <Can permission="orders:create">
 * - OrderDetailModal (holat o'zgartirish bilan)
 * - CreateOrderModal
 * - i18n uz/ru
 */

import {
  Badge,
  Box,
  Button,
  Group,
  Loader,
  Pagination,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { IconEye, IconPlus, IconTemplate, IconTruck } from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Can } from "@/rbac/Can";
import { useOrders } from "./api/ordersApi";
import { OrderStatusBadge } from "./components/OrderStatusBadge";
import { OrderDetailModal } from "./components/OrderDetailModal";
import { CreateOrderModal } from "./components/CreateOrderModal";
import { OrderTemplatesModal } from "./components/OrderTemplatesModal";
import { AssignCourierModal } from "@/features/delivery/components/AssignCourierModal";
import type { OrderOut, OrderStatus } from "./types";

const PAGE_SIZE = 20;

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "orders.filter.all_statuses" },
  { value: "confirmed", label: "orders.status.confirmed" },
  { value: "packed", label: "orders.status.packed" },
  { value: "delivering", label: "orders.status.delivering" },
  { value: "delivered", label: "orders.status.delivered" },
  { value: "canceled", label: "orders.status.canceled" },
];

export function OrderListPage() {
  const { t } = useTranslation();

  // Filtrlar
  const [statusFilter, setStatusFilter] = useState<OrderStatus | null>(null);
  const [fromDate, setFromDate] = useState<string>("");
  const [toDate, setToDate] = useState<string>("");

  // Sahifalash
  const [page, setPage] = useState(1);
  const offset = (page - 1) * PAGE_SIZE;

  // Modal holatlari
  const [detailOpened, { open: openDetail, close: closeDetail }] = useDisclosure(false);
  const [createOpened, { open: openCreate, close: closeCreate }] = useDisclosure(false);
  const [assignOpened, { open: openAssign, close: closeAssign }] = useDisclosure(false);
  const [templatesOpened, { open: openTemplates, close: closeTemplates }] = useDisclosure(false);
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);
  const [selectedAssignOrder, setSelectedAssignOrder] = useState<OrderOut | null>(null);

  // API
  const { data, isLoading, isError, error } = useOrders({
    status: statusFilter,
    from: fromDate || undefined,
    to: toDate || undefined,
    limit: PAGE_SIZE,
    offset,
  });

  const handleViewOrder = (orderId: string) => {
    setSelectedOrderId(orderId);
    openDetail();
  };

  const handleAssignCourier = (order: OrderOut) => {
    setSelectedAssignOrder(order);
    openAssign();
  };

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1;

  return (
    <Stack gap="md">
      {/* Sarlavha va yaratish tugmasi */}
      <Group justify="space-between">
        <Title order={3}>{t("pages.orders.title")}</Title>
        <Group gap="sm">
          <Can permission="orders:create">
            <Button
              variant="subtle"
              leftSection={<IconTemplate size={16} />}
              onClick={openTemplates}
            >
              {t("orders.templates.menu_btn", {
                defaultValue: "Shablonlar",
              })}
            </Button>
          </Can>
          <Can permission="orders:create">
            <Button
              leftSection={<IconPlus size={16} />}
              onClick={openCreate}
            >
              {t("orders.actions.create")}
            </Button>
          </Can>
        </Group>
      </Group>

      {/* Filtrlar */}
      <Group gap="sm" wrap="wrap">
        <Select
          placeholder={t("orders.filter.all_statuses")}
          data={STATUS_OPTIONS.map((o) => ({
            value: o.value,
            label: t(o.label),
          }))}
          value={statusFilter ?? ""}
          onChange={(v) => {
            setStatusFilter((v as OrderStatus) || null);
            setPage(1);
          }}
          w={180}
          clearable
          aria-label={t("orders.filter.status")}
        />
        <TextInput
          placeholder={t("orders.filter.from")}
          type="date"
          value={fromDate}
          onChange={(e) => {
            setFromDate(e.currentTarget.value);
            setPage(1);
          }}
          w={160}
          aria-label={t("orders.filter.from")}
        />
        <TextInput
          placeholder={t("orders.filter.to")}
          type="date"
          value={toDate}
          onChange={(e) => {
            setToDate(e.currentTarget.value);
            setPage(1);
          }}
          w={160}
          aria-label={t("orders.filter.to")}
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
          <Text c="dimmed">{t("orders.table.empty")}</Text>
        </Box>
      ) : (
        <Table.ScrollContainer minWidth={700}>
          <Table striped highlightOnHover withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t("orders.table.number")}</Table.Th>
                <Table.Th>{t("orders.table.date")}</Table.Th>
                <Table.Th>{t("orders.table.store")}</Table.Th>
                <Table.Th>{t("orders.table.mode")}</Table.Th>
                <Table.Th>{t("orders.table.status")}</Table.Th>
                <Table.Th ta="right">{t("orders.table.amount")}</Table.Th>
                <Table.Th>{t("orders.table.actions")}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.items.map((order) => (
                <Table.Tr key={order.id}>
                  <Table.Td>
                    <Text size="sm" fw={500} ff="monospace">
                      {order.id.slice(0, 8).toUpperCase()}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">
                      {new Date(order.ordered_at).toLocaleDateString()}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" ff="monospace" lineClamp={1}>
                      {order.store_id.slice(0, 8)}...
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Badge variant="outline" size="sm">
                      {order.mode}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <OrderStatusBadge status={order.status} />
                  </Table.Td>
                  <Table.Td ta="right">
                    <Text size="sm" fw={500}>
                      {Number(order.total_amount).toLocaleString()} {order.currency}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Group gap={4} wrap="nowrap">
                      <Tooltip label={t("orders.actions.view")}>
                        <Button
                          variant="subtle"
                          size="xs"
                          leftSection={<IconEye size={14} />}
                          onClick={() => handleViewOrder(order.id)}
                        >
                          {t("orders.actions.view")}
                        </Button>
                      </Tooltip>
                      {order.status === "confirmed" && (
                        <Can permission="delivery:create">
                          <Tooltip
                            label={t("delivery.assign_courier.title", {
                              defaultValue: "Kuryer tayinlash",
                            })}
                          >
                            <Button
                              variant="subtle"
                              size="xs"
                              color="teal"
                              leftSection={<IconTruck size={14} />}
                              onClick={() => handleAssignCourier(order)}
                            >
                              {t("delivery.actions.assign_courier")}
                            </Button>
                          </Tooltip>
                        </Can>
                      )}
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <Group justify="center">
          <Pagination
            value={page}
            onChange={setPage}
            total={totalPages}
            size="sm"
          />
        </Group>
      )}

      {/* Modallar */}
      <OrderDetailModal
        opened={detailOpened}
        onClose={closeDetail}
        orderId={selectedOrderId}
      />
      <CreateOrderModal opened={createOpened} onClose={closeCreate} />
      <OrderTemplatesModal opened={templatesOpened} onClose={closeTemplates} />
      <AssignCourierModal
        opened={assignOpened}
        onClose={closeAssign}
        order={selectedAssignOrder}
      />
    </Stack>
  );
}
