/**
 * PosSalesListPage — POS sotuvlar ro'yxati + kunlik summary kartalari.
 *
 * Xususiyatlar:
 * - Bugungi kunlik summary (umumiy sotuv, summa, naqd/karta breakdown)
 * - Paginated sotuvlar jadvali
 * - Sana filtr (date_from / date_to)
 * - store_id filtr (store roli uchun avtomatik, admin/buxgalter uchun ixtiyoriy)
 * - RBAC: pos:create → "Yangi sotuv" tugmasi
 * - i18n defaultValue
 */

import {
  Badge,
  Button,
  Card,
  Group,
  Loader,
  Pagination,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { DatePickerInput } from "@mantine/dates";
import {
  IconCash,
  IconCreditCard,
  IconPlus,
  IconReceipt,
} from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Can } from "@/rbac/Can";
import { usePosSales, usePosSummary } from "./api/posApi";
import { toLocalYMD } from "@/utils/date";

const PAGE_SIZE = 20;

// ─── Kunlik summary kartasi ────────────────────────────────────────────────────

interface SummaryCardProps {
  label: string;
  value: string | number;
  icon: React.ComponentType<{ size?: number | string }>;
}

function SummaryCard({ label, value, icon: Icon }: SummaryCardProps) {
  return (
    <Card shadow="sm" padding="md" radius="md" withBorder>
      <Group justify="space-between" mb="xs">
        <Text size="sm" c="dimmed">
          {label}
        </Text>
        <Icon size={20} />
      </Group>
      <Text fw={700} size="xl">
        {value}
      </Text>
    </Card>
  );
}

// ─── Komponent ────────────────────────────────────────────────────────────────

interface PosSalesListPageProps {
  /** Do'kon roli uchun store_id avtomatik beriladi */
  storeId?: string;
  /** Yangi sotuv sahifasiga o'tish */
  onNewSale?: () => void;
}

export function PosSalesListPage({ storeId, onNewSale }: PosSalesListPageProps) {
  const { t } = useTranslation();

  // Filtrlar
  const [dateFrom, setDateFrom] = useState<Date | null>(null);
  const [dateTo, setDateTo] = useState<Date | null>(null);
  const [storeIdFilter, setStoreIdFilter] = useState(storeId ?? "");

  // Sahifalash
  const [page, setPage] = useState(1);
  const offset = (page - 1) * PAGE_SIZE;

  // API
  // FIX #1: toLocalYMD — UTC emas, mahalliy sana (UZ UTC+5 tongida noto'g'ri kun muammosi yo'q)
  const todayStr = toLocalYMD(new Date());
  // FIX #4: summary ham storeIdFilter || storeId ishlatadi — ro'yxat bilan bir xil scope
  const effectiveStoreId = storeIdFilter || storeId;
  const { data: summary, isLoading: summaryLoading } = usePosSummary(
    todayStr,
    effectiveStoreId,
  );

  const { data: salesData, isLoading: salesLoading } = usePosSales({
    store_id: storeIdFilter || undefined,
    // FIX #1: mahalliy sana chegaralari — backend YYYY-MM-DD kutadi
    date_from: dateFrom ? toLocalYMD(dateFrom) : undefined,
    date_to: dateTo ? toLocalYMD(dateTo) : undefined,
    limit: PAGE_SIZE,
    offset,
  });

  const totalPages = salesData ? Math.ceil(salesData.total / PAGE_SIZE) : 1;

  // Naqd/karta summary
  const cashEntry = summary?.by_payment.find(
    (p) => p.payment_method === "cash",
  );
  const cardEntry = summary?.by_payment.find(
    (p) => p.payment_method === "card",
  );

  return (
    <Stack gap="md">
      {/* Sarlavha */}
      <Group justify="space-between">
        <Title order={3} defaultValue={t("pos.title", "POS — Savdo kassasi")}>
          {t("pos.title", "POS — Savdo kassasi")}
        </Title>
        <Can permission="pos:create">
          <Button
            leftSection={<IconPlus size={16} />}
            onClick={onNewSale}
          >
            {t("pos.actions.new_sale", "Yangi sotuv")}
          </Button>
        </Can>
      </Group>

      {/* Kunlik summary kartalari */}
      {summaryLoading ? (
        <Loader size="sm" />
      ) : summary ? (
        <SimpleGrid cols={{ base: 2, sm: 4 }}>
          <SummaryCard
            label={t("pos.daily_report.total_sales", "Jami sotuvlar")}
            value={summary.total_sales}
            icon={IconReceipt}
          />
          <SummaryCard
            label={t("pos.daily_report.total_amount", "Umumiy summa")}
            value={Number(summary.total_amount).toLocaleString()}
            icon={IconCash}
          />
          <SummaryCard
            label={t("pos.daily_report.cash_amount", "Naqd")}
            value={
              cashEntry
                ? Number(cashEntry.total_amount).toLocaleString()
                : "0"
            }
            icon={IconCash}
          />
          <SummaryCard
            label={t("pos.daily_report.card_amount", "Karta")}
            value={
              cardEntry
                ? Number(cardEntry.total_amount).toLocaleString()
                : "0"
            }
            icon={IconCreditCard}
          />
        </SimpleGrid>
      ) : null}

      {/* Filtrlar */}
      <Group gap="sm" wrap="wrap">
        <DatePickerInput
          label={t("orders.filter.from", "Dan")}
          placeholder="YYYY-MM-DD"
          value={dateFrom}
          onChange={setDateFrom}
          clearable
          w={160}
        />
        <DatePickerInput
          label={t("orders.filter.to", "Gacha")}
          placeholder="YYYY-MM-DD"
          value={dateTo}
          onChange={setDateTo}
          clearable
          w={160}
        />
        {!storeId && (
          <TextInput
            label="Store ID"
            placeholder="UUID..."
            value={storeIdFilter}
            onChange={(e) => {
              setStoreIdFilter(e.currentTarget.value);
              setPage(1);
            }}
            w={220}
          />
        )}
      </Group>

      {/* Jadval */}
      {salesLoading ? (
        <Loader size="sm" />
      ) : (
        <>
          <Table.ScrollContainer minWidth={600}>
            <Table highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t("pos.receipt.date", "Sana")}</Table.Th>
                  <Table.Th>
                    {t("pos.payment.method", "To'lov usuli")}
                  </Table.Th>
                  <Table.Th>
                    {t("pos.cart.total", "Umumiy summa")}
                  </Table.Th>
                  <Table.Th>
                    {t("pos.receipt.items", "Mahsulotlar")}
                  </Table.Th>
                  <Table.Th>Holat</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {salesData?.items.length === 0 ? (
                  <Table.Tr>
                    <Table.Td colSpan={5}>
                      <Text ta="center" c="dimmed" py="md">
                        {t("pos.daily_report.empty", "Bugun sotuvlar yo'q")}
                      </Text>
                    </Table.Td>
                  </Table.Tr>
                ) : (
                  salesData?.items.map((sale) => (
                    <Table.Tr key={sale.id}>
                      <Table.Td>
                        {new Date(sale.created_at).toLocaleString()}
                      </Table.Td>
                      <Table.Td>
                        <Badge variant="light" color="blue">
                          {sale.payment_method === "cash"
                            ? t("pos.payment.cash", "Naqd")
                            : t("pos.payment.card", "Karta")}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        {Number(sale.total_amount).toLocaleString()} UZS
                      </Table.Td>
                      <Table.Td>{sale.lines.length}</Table.Td>
                      <Table.Td>
                        <Badge
                          color={
                            sale.status === "completed" ? "green" : "gray"
                          }
                          variant="light"
                        >
                          {sale.status}
                        </Badge>
                      </Table.Td>
                    </Table.Tr>
                  ))
                )}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>

          {totalPages > 1 && (
            <Pagination
              value={page}
              onChange={setPage}
              total={totalPages}
              mt="sm"
            />
          )}
        </>
      )}
    </Stack>
  );
}
