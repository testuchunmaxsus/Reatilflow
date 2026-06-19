/**
 * StatsDashboardPage — savdo, yetkazish va moliyaviy statistika.
 *
 * Xususiyatlar:
 * - Savdo: davr bo'yicha chiziq grafik (recharts) — /stats/sales?group_by=
 * - Yetkazish: status bo'yicha (delivered/failed/in_progress), o'rtacha vaqt
 * - Moliyaviy: faqat <Can permission="finance:view"> — buxgalter/admin ko'radi
 * - Davr tanlash (from/to date picker), group_by (kun/hafta/oy)
 * - RBAC-aware: kuryer moliyaviy bo'limni ko'rmaydi (403/yashirin)
 * - i18n uz/ru
 */

import {
  Badge,
  Box,
  Card,
  Divider,
  Group,
  Loader,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Legend,
} from "recharts";
import { Can } from "@/rbac/Can";
import { usePermissions } from "@/rbac/usePermissions";
import { useSalesStats, useDeliveryStats, useFinanceStats } from "./api/statsApi";
import type { GroupBy } from "./types";

// ─── Yordamchi komponentlar ────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  color = "blue",
}: {
  label: string;
  value: string | number;
  color?: string;
}) {
  return (
    <Card withBorder padding="md" radius="sm">
      <Text size="xs" c="dimmed" mb={4}>
        {label}
      </Text>
      <Text fw={700} size="xl" c={color}>
        {value}
      </Text>
    </Card>
  );
}

// ─── Asosiy sahifa ─────────────────────────────────────────────────────────────

export function StatsDashboardPage() {
  const { t } = useTranslation();
  const { can } = usePermissions();
  const canViewFinance = can("finance:view");

  // Davr filtrlari — ISO date string (YYYY-MM-DD)
  const [fromDate, setFromDate] = useState<string>("");
  const [toDate, setToDate] = useState<string>("");
  const [groupBy, setGroupBy] = useState<GroupBy>("day");

  const filters = {
    from: fromDate || undefined,
    to: toDate || undefined,
    group_by: groupBy,
  };

  const {
    data: salesData,
    isLoading: salesLoading,
    isError: salesError,
  } = useSalesStats(filters);

  const {
    data: deliveryData,
    isLoading: deliveryLoading,
    isError: deliveryError,
  } = useDeliveryStats({
    from: filters.from,
    to: filters.to,
  });

  // Finance — faqat ruxsat bo'lsa yuboriladi (courier 403 den saqlanish)
  const {
    data: financeData,
    isLoading: financeLoading,
    isError: financeError,
  } = useFinanceStats(
    { from: filters.from, to: filters.to },
    canViewFinance,
  );

  // Recharts uchun ma'lumotlar
  const salesChartData = (salesData?.dynamics ?? []).map((d) => ({
    period: d.period,
    count: d.order_count,
    amount: Number(d.total_amount),
  }));

  return (
    <Stack gap="xl">
      <Title order={3}>{t("pages.stats.title")}</Title>

      {/* Davr va group_by tanlash */}
      <Group gap="sm" wrap="wrap">
        <TextInput
          label={t("stats.filter.from")}
          type="date"
          value={fromDate}
          onChange={(e) => setFromDate(e.currentTarget.value)}
          w={160}
        />
        <TextInput
          label={t("stats.filter.to")}
          type="date"
          value={toDate}
          onChange={(e) => setToDate(e.currentTarget.value)}
          w={160}
        />
        <Select
          label={t("stats.filter.group_by")}
          data={[
            { value: "day", label: t("stats.group_by.day") },
            { value: "week", label: t("stats.group_by.week") },
            { value: "month", label: t("stats.group_by.month") },
          ]}
          value={groupBy}
          onChange={(v) => setGroupBy((v as GroupBy) ?? "day")}
          w={160}
        />
      </Group>

      <Divider label={t("stats.sections.sales")} labelPosition="left" />

      {/* ─── Savdo bo'limi ─── */}
      {salesLoading ? (
        <Group justify="center" py="md">
          <Loader size="sm" />
          <Text c="dimmed">{t("common.loading")}</Text>
        </Group>
      ) : salesError ? (
        <Text c="red">{t("errors.unknown")}</Text>
      ) : (
        <Stack gap="md">
          <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }}>
            <StatCard
              label={t("stats.sales.total_orders")}
              value={salesData?.total_orders ?? 0}
              color="blue"
            />
            <StatCard
              label={t("stats.sales.total_amount")}
              value={`${Number(salesData?.total_amount ?? 0).toLocaleString()} ${salesData?.currency ?? "UZS"}`}
              color="teal"
            />
            <StatCard
              label={t("stats.filter.period")}
              value={
                salesData?.period_from
                  ? `${salesData.period_from.slice(0, 10)} — ${salesData.period_to?.slice(0, 10) ?? "..."}`
                  : t("stats.filter.all_time")
              }
              color="gray"
            />
          </SimpleGrid>

          {/* Grafik */}
          {salesChartData.length > 0 ? (
            <Card withBorder padding="md">
              <Text fw={500} mb="sm" size="sm">
                {t("stats.sales.dynamics_chart")}
              </Text>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={salesChartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                  <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
                  <YAxis
                    yAxisId="right"
                    orientation="right"
                    tick={{ fontSize: 11 }}
                  />
                  <RechartsTooltip />
                  <Legend />
                  <Bar
                    yAxisId="left"
                    dataKey="count"
                    name={t("stats.sales.order_count")}
                    fill="#339af0"
                  />
                  <Bar
                    yAxisId="right"
                    dataKey="amount"
                    name={t("stats.sales.amount")}
                    fill="#51cf66"
                  />
                </BarChart>
              </ResponsiveContainer>
            </Card>
          ) : (
            <Box py="md" ta="center">
              <Text c="dimmed">{t("stats.sales.no_dynamics")}</Text>
            </Box>
          )}
        </Stack>
      )}

      <Divider label={t("stats.sections.delivery")} labelPosition="left" />

      {/* ─── Yetkazish bo'limi ─── */}
      {deliveryLoading ? (
        <Group justify="center" py="md">
          <Loader size="sm" />
          <Text c="dimmed">{t("common.loading")}</Text>
        </Group>
      ) : deliveryError ? (
        <Text c="red">{t("errors.unknown")}</Text>
      ) : (
        <Stack gap="md">
          <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }}>
            <StatCard
              label={t("stats.delivery.total")}
              value={deliveryData?.total_deliveries ?? 0}
              color="blue"
            />
            <StatCard
              label={t("stats.delivery.delivered")}
              value={deliveryData?.delivered_count ?? 0}
              color="green"
            />
            <StatCard
              label={t("stats.delivery.failed")}
              value={deliveryData?.failed_count ?? 0}
              color="red"
            />
            <StatCard
              label={t("stats.delivery.in_progress")}
              value={deliveryData?.in_progress_count ?? 0}
              color="orange"
            />
          </SimpleGrid>

          {deliveryData && (
            <Card withBorder padding="md">
              <Group gap="xl" wrap="wrap">
                <Box>
                  <Text size="xs" c="dimmed">
                    {t("stats.delivery.avg_minutes")}
                  </Text>
                  <Text fw={600} size="lg">
                    {deliveryData.avg_delivery_minutes !== null
                      ? `${deliveryData.avg_delivery_minutes} ${t("stats.delivery.minutes")}`
                      : "—"}
                  </Text>
                </Box>

                {/* Yetkazish nisbati chiziq grafiği */}
                {deliveryData.total_deliveries > 0 && (
                  <Box style={{ flex: 1, minWidth: 200 }}>
                    <Text size="xs" c="dimmed" mb={4}>
                      {t("stats.delivery.distribution")}
                    </Text>
                    <ResponsiveContainer width="100%" height={120}>
                      <BarChart
                        data={[
                          {
                            name: t("stats.delivery.delivered"),
                            value: deliveryData.delivered_count,
                          },
                          {
                            name: t("stats.delivery.failed"),
                            value: deliveryData.failed_count,
                          },
                          {
                            name: t("stats.delivery.in_progress"),
                            value: deliveryData.in_progress_count,
                          },
                        ]}
                        layout="vertical"
                      >
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis type="number" tick={{ fontSize: 11 }} />
                        <YAxis
                          dataKey="name"
                          type="category"
                          width={80}
                          tick={{ fontSize: 10 }}
                        />
                        <RechartsTooltip />
                        <Bar dataKey="value" fill="#339af0" />
                      </BarChart>
                    </ResponsiveContainer>
                  </Box>
                )}
              </Group>
            </Card>
          )}
        </Stack>
      )}

      {/* ─── Moliyaviy bo'lim (faqat finance:view) ─── */}
      <Can
        permission="finance:view"
        fallback={null}
      >
        <>
          <Divider label={t("stats.sections.finance")} labelPosition="left" />

          {financeLoading ? (
            <Group justify="center" py="md">
              <Loader size="sm" />
              <Text c="dimmed">{t("common.loading")}</Text>
            </Group>
          ) : financeError ? (
            <Text c="red">{t("errors.unknown")}</Text>
          ) : financeData ? (
            <Stack gap="md">
              <SimpleGrid cols={{ base: 1, sm: 3 }}>
                <StatCard
                  label={t("stats.finance.total_debit")}
                  value={`${Number(financeData.total_debit).toLocaleString()} UZS`}
                  color="red"
                />
                <StatCard
                  label={t("stats.finance.total_credit")}
                  value={`${Number(financeData.total_credit).toLocaleString()} UZS`}
                  color="green"
                />
                <StatCard
                  label={t("stats.finance.net_balance")}
                  value={`${Number(financeData.net_balance).toLocaleString()} UZS`}
                  color={Number(financeData.net_balance) >= 0 ? "orange" : "teal"}
                />
              </SimpleGrid>

              {/* Do'kon bo'yicha qarz/haqdorlik jadvali */}
              {financeData.stores.length > 0 ? (
                <Table.ScrollContainer minWidth={600}>
                  <Table striped withTableBorder>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>{t("stats.finance.store_name")}</Table.Th>
                        <Table.Th ta="right">{t("stats.finance.debit")}</Table.Th>
                        <Table.Th ta="right">{t("stats.finance.credit")}</Table.Th>
                        <Table.Th ta="right">{t("stats.finance.balance")}</Table.Th>
                        <Table.Th>{t("stats.finance.status_label")}</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {financeData.stores.map((s) => (
                        <Table.Tr key={s.store_id}>
                          <Table.Td>
                            <Text size="sm" fw={500}>
                              {s.store_name}
                            </Text>
                          </Table.Td>
                          <Table.Td ta="right">
                            <Text size="sm">
                              {Number(s.total_debit).toLocaleString()}
                            </Text>
                          </Table.Td>
                          <Table.Td ta="right">
                            <Text size="sm">
                              {Number(s.total_credit).toLocaleString()}
                            </Text>
                          </Table.Td>
                          <Table.Td ta="right">
                            <Text
                              size="sm"
                              fw={600}
                              c={Number(s.balance) > 0 ? "red" : "green"}
                            >
                              {Number(s.balance).toLocaleString()} {s.currency}
                            </Text>
                          </Table.Td>
                          <Table.Td>
                            <Badge
                              color={Number(s.balance) > 0 ? "red" : "green"}
                              variant="light"
                              size="sm"
                            >
                              {Number(s.balance) > 0
                                ? t("stats.finance.debtor")
                                : t("stats.finance.creditor")}
                            </Badge>
                          </Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Table.ScrollContainer>
              ) : (
                <Box py="md" ta="center">
                  <Text c="dimmed">{t("stats.finance.no_stores")}</Text>
                </Box>
              )}
            </Stack>
          ) : null}
        </>
      </Can>
    </Stack>
  );
}
