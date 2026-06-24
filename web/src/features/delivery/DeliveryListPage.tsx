/**
 * DeliveryListPage — yetkazishlar ro'yxati.
 *
 * RBAC scope (backend tomonidan boshqariladi):
 *   courier  → faqat o'ziga tayinlangan yetkazishlar
 *   agent    → o'z buyurtmalari yetkazishlari
 *   store    → o'z buyurtmalari yetkazishlari
 *   admin    → barchasi (courier_id filtri ko'rinadi)
 *
 * Filtrlar: holat, sana oralig'i.
 * i18n: uz/ru, defaultValue bilan.
 */

import {
  Box,
  Button,
  Group,
  Loader,
  Pagination,
  Select,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useDeliveries } from "./api/deliveryApi";
import type { Delivery } from "./types";
// FIX #11: umumiy komponent — DeliveryDetailPage ham shu fayldan import qiladi
import { DeliveryStatusBadge } from "./components/DeliveryStatusBadge";

const PAGE_SIZE = 20;

// ─── Sana formatlash ─────────────────────────────────────────────────────────

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString();
}

// ─── Asosiy komponent ────────────────────────────────────────────────────────

export function DeliveryListPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const offset = (page - 1) * PAGE_SIZE;

  const { data, isLoading, isError, error } = useDeliveries({
    status: statusFilter || undefined,
    limit: PAGE_SIZE,
    offset,
  });

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1;

  const statusOptions = [
    { value: "", label: t("delivery.filter.all_statuses", { defaultValue: "Barcha holatlar" }) },
    { value: "assigned", label: t("delivery.status.assigned", { defaultValue: "Tayinlangan" }) },
    { value: "started", label: t("delivery.status.started", { defaultValue: "Yo'lda" }) },
    { value: "delivering", label: t("delivery.status.delivering", { defaultValue: "Yetkazilmoqda" }) },
    { value: "delivered", label: t("delivery.status.delivered", { defaultValue: "Yetkazildi" }) },
    { value: "failed", label: t("delivery.status.failed", { defaultValue: "Muvaffaqiyatsiz" }) },
  ];

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Title order={3}>
          {t("delivery.title", { defaultValue: "Yetkazish" })}
        </Title>
      </Group>

      {/* Filtrlar */}
      <Group gap="sm">
        <Select
          data={statusOptions}
          value={statusFilter}
          onChange={(v) => {
            setStatusFilter(v ?? "");
            setPage(1);
          }}
          w={200}
          aria-label={t("delivery.filter.all_statuses", { defaultValue: "Barcha holatlar" })}
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
          <Text c="dimmed">
            {t("delivery.table.empty", { defaultValue: "Yetkazishlar topilmadi" })}
          </Text>
        </Box>
      ) : (
        <Table.ScrollContainer minWidth={900}>
          <Table striped highlightOnHover withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>
                  {t("delivery.table.order_number", { defaultValue: "Buyurtma" })}
                </Table.Th>
                <Table.Th>
                  {t("delivery.table.courier", { defaultValue: "Kuryer" })}
                </Table.Th>
                <Table.Th>
                  {t("delivery.table.status", { defaultValue: "Holat" })}
                </Table.Th>
                <Table.Th>
                  {t("delivery.table.assigned_at", { defaultValue: "Tayinlangan" })}
                </Table.Th>
                <Table.Th>
                  {t("delivery.table.delivered_at", { defaultValue: "Yetkazilgan" })}
                </Table.Th>
                <Table.Th>
                  {t("delivery.table.actions", { defaultValue: "Amallar" })}
                </Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.items.map((delivery: Delivery) => (
                <Table.Tr key={delivery.id}>
                  <Table.Td>
                    <Text size="sm" ff="monospace">
                      {delivery.order_id.slice(0, 8)}…
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" ff="monospace">
                      {delivery.courier_id.slice(0, 8)}…
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <DeliveryStatusBadge status={delivery.status} />
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed">
                      {formatDate(delivery.assigned_at)}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed">
                      {formatDate(delivery.delivered_at)}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Button
                      variant="subtle"
                      size="xs"
                      onClick={() => navigate(`/delivery/${delivery.id}`)}
                    >
                      {t("common.edit", { defaultValue: "Ko'rish" })}
                    </Button>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}

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
    </Stack>
  );
}
