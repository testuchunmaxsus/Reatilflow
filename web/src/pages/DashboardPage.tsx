/**
 * DashboardPage — bosh sahifa: jonli statistika widgetlari.
 *
 * Widgetlar (TanStack Query):
 *   - Jami do'konlar     (customers:view)  → GET /customers/stores  .total
 *   - Jami mahsulotlar   (catalog:view)    → GET /catalog/products   .total
 *   - Jami foydalanuvchilar (rbac:view)    → GET /users              .total
 *   - Savdo             (stats:view)       → GET /stats/sales        total_orders + total_amount
 *   - Moliyaviy holat   (finance:view)     → GET /stats/finance      net_balance
 *
 * Har karta <Can permission="..."> bilan himoyalangan.
 * Yuklanish / xato holatlari ko'rsatiladi.
 */

import {
  Box,
  Card,
  Grid,
  Group,
  Loader,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import {
  IconBuildingStore,
  IconPackage,
  IconUsers,
  IconShoppingCart,
  IconCash,
} from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/auth/AuthContext";
import { usePermissions } from "@/rbac/usePermissions";
import { Can } from "@/rbac/Can";
import { useStores } from "@/features/customers/api/customersApi";
import { useProducts } from "@/features/catalog/api/catalogApi";
import { useUsers } from "@/features/users/api/usersApi";
import { useSalesStats, useFinanceStats } from "@/features/stats/api/statsApi";

// ─── Raqamni formatlash yordamchisi ─────────────────────────────────────────

function formatAmount(value: string | number): string {
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) return String(value);
  return new Intl.NumberFormat("uz-UZ").format(Math.round(num));
}

// ─── Widget kadrchasi ────────────────────────────────────────────────────────

interface StatCardProps {
  icon: React.ReactNode;
  color: string;
  label: string;
  value: string | number | undefined;
  sub?: string;
  loading?: boolean;
  error?: string | null;
}

function StatCard({
  icon,
  color,
  label,
  value,
  sub,
  loading,
  error,
}: StatCardProps) {
  return (
    <Card shadow="sm" padding="lg" radius="md" withBorder h="100%">
      <Group gap="sm" mb="xs">
        <ThemeIcon size={36} radius="md" color={color} variant="light">
          {icon}
        </ThemeIcon>
        <Text fw={500} size="sm" c="dimmed">
          {label}
        </Text>
      </Group>

      {loading ? (
        <Group gap="xs" mt={4}>
          <Loader size="xs" />
          <Text size="sm" c="dimmed">...</Text>
        </Group>
      ) : error ? (
        <Text size="sm" c="red" mt={4}>
          {error}
        </Text>
      ) : (
        <>
          <Text fw={700} size="xl" mt={4}>
            {value ?? "—"}
          </Text>
          {sub && (
            <Text size="xs" c="dimmed" mt={2}>
              {sub}
            </Text>
          )}
        </>
      )}
    </Card>
  );
}

// ─── Bosh komponent ──────────────────────────────────────────────────────────

export function DashboardPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { role, can } = usePermissions();

  // ─── API so'rovlari ────────────────────────────────────────────────────────
  const storesQuery = useStores({ limit: 1 });
  const productsQuery = useProducts({ limit: 1 });
  const usersQuery = useUsers({ limit: 1 });
  const salesQuery = useSalesStats();
  const financeQuery = useFinanceStats({}, can("finance:view"));

  return (
    <Box>
      <Title order={3} mb="xs">
        {t("pages.dashboard.title")}
      </Title>

      <Text c="dimmed" mb="xl">
        {user ? t("common.welcome", { name: user.full_name }) : ""}
        {role && ` — ${t(`common.role.${role}`)}`}
      </Text>

      <Grid gutter="md">
        {/* Jami do'konlar */}
        <Can permission="customers:view">
          <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
            <StatCard
              icon={<IconBuildingStore size={20} />}
              color="blue"
              label={t("dashboard.cards.total_stores")}
              value={storesQuery.data?.total}
              loading={storesQuery.isLoading}
              error={
                storesQuery.isError
                  ? (storesQuery.error instanceof Error
                      ? storesQuery.error.message
                      : t("errors.unknown"))
                  : null
              }
            />
          </Grid.Col>
        </Can>

        {/* Jami mahsulotlar */}
        <Can permission="catalog:view">
          <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
            <StatCard
              icon={<IconPackage size={20} />}
              color="teal"
              label={t("dashboard.cards.total_products")}
              value={productsQuery.data?.total}
              loading={productsQuery.isLoading}
              error={
                productsQuery.isError
                  ? (productsQuery.error instanceof Error
                      ? productsQuery.error.message
                      : t("errors.unknown"))
                  : null
              }
            />
          </Grid.Col>
        </Can>

        {/* Jami foydalanuvchilar */}
        <Can permission="rbac:view">
          <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
            <StatCard
              icon={<IconUsers size={20} />}
              color="violet"
              label={t("dashboard.cards.total_users")}
              value={usersQuery.data?.total}
              loading={usersQuery.isLoading}
              error={
                usersQuery.isError
                  ? (usersQuery.error instanceof Error
                      ? usersQuery.error.message
                      : t("errors.unknown"))
                  : null
              }
            />
          </Grid.Col>
        </Can>

        {/* Savdo statistikasi */}
        <Can permission="stats:view">
          <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
            <StatCard
              icon={<IconShoppingCart size={20} />}
              color="orange"
              label={t("dashboard.cards.sales")}
              value={
                salesQuery.data
                  ? String(salesQuery.data.total_orders)
                  : undefined
              }
              sub={
                salesQuery.data
                  ? `${formatAmount(salesQuery.data.total_amount)} ${salesQuery.data.currency}`
                  : undefined
              }
              loading={salesQuery.isLoading}
              error={
                salesQuery.isError
                  ? (salesQuery.error instanceof Error
                      ? salesQuery.error.message
                      : t("errors.unknown"))
                  : null
              }
            />
          </Grid.Col>
        </Can>

        {/* Moliyaviy holat */}
        <Can permission="finance:view">
          <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
            <StatCard
              icon={<IconCash size={20} />}
              color={
                financeQuery.data
                  ? parseFloat(financeQuery.data.net_balance) >= 0
                    ? "green"
                    : "red"
                  : "gray"
              }
              label={t("dashboard.cards.net_balance")}
              value={
                financeQuery.data
                  ? `${formatAmount(financeQuery.data.net_balance)} UZS`
                  : undefined
              }
              sub={
                financeQuery.data
                  ? parseFloat(financeQuery.data.net_balance) >= 0
                    ? t("stats.finance.creditor")
                    : t("stats.finance.debtor")
                  : undefined
              }
              loading={financeQuery.isLoading}
              error={
                financeQuery.isError
                  ? (financeQuery.error instanceof Error
                      ? financeQuery.error.message
                      : t("errors.unknown"))
                  : null
              }
            />
          </Grid.Col>
        </Can>
      </Grid>
    </Box>
  );
}
