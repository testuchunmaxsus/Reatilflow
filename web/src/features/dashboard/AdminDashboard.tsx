/**
 * AdminDashboard — administrator bosh sahifasi.
 *
 * Widgetlar:
 *   - Jami do'konlar         (customers:view) → useStores
 *   - Jami mahsulotlar       (catalog:view)   → useProducts
 *   - Jami foydalanuvchilar  (rbac:view)      → useUsers
 *   - Savdo statistikasi     (stats:view)     → useSalesStats
 *   - Moliyaviy holat        (finance:view)   → useFinanceStats
 * Tezkor havolalar: /analytics, /import, /marketplace, /users
 */

import {
  Box,
  Grid,
  SimpleGrid,
  Text,
  Title,
} from "@mantine/core";
import {
  IconBuildingStore,
  IconPackage,
  IconUsers,
  IconShoppingCart,
  IconCash,
  IconBrain,
  IconFileImport,
  IconShoppingBag,
  IconChartBar,
} from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/auth/AuthContext";
import { usePermissions } from "@/rbac/usePermissions";
import { Can } from "@/rbac/Can";
import { useStores } from "@/features/customers/api/customersApi";
import { useProducts } from "@/features/catalog/api/catalogApi";
import { useUsers } from "@/features/users/api/usersApi";
import { useSalesStats, useFinanceStats } from "@/features/stats/api/statsApi";
import { StatCard, formatAmount } from "./components/StatCard";
import { QuickLinkCard } from "./components/QuickLinkCard";

export function AdminDashboard() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { role, can } = usePermissions();

  const storesQuery = useStores({ limit: 1 });
  const productsQuery = useProducts({ limit: 1 });
  const usersQuery = useUsers({ limit: 1 });
  const salesQuery = useSalesStats();
  const financeQuery = useFinanceStats({}, can("finance:view"));

  return (
    <Box>
      <Title order={3} mb="xs">
        {t("pages.dashboard.title", { defaultValue: "Bosh sahifa" })}
      </Title>
      <Text c="dimmed" mb="xl">
        {user ? t("common.welcome", { name: user.full_name, defaultValue: `Xush kelibsiz, ${user.full_name}` }) : ""}
        {role && ` — ${t(`common.role.${role}`, { defaultValue: role })}`}
      </Text>

      {/* KPI kartalar */}
      <Grid gutter="md" mb="xl">
        <Can permission="customers:view">
          <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
            <StatCard
              icon={<IconBuildingStore size={20} />}
              color="blue"
              label={t("dashboard.cards.total_stores", { defaultValue: "Jami do'konlar" })}
              value={storesQuery.data?.total}
              loading={storesQuery.isLoading}
              error={storesQuery.isError ? (storesQuery.error instanceof Error ? storesQuery.error.message : t("errors.unknown", { defaultValue: "Xato" })) : null}
            />
          </Grid.Col>
        </Can>

        <Can permission="catalog:view">
          <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
            <StatCard
              icon={<IconPackage size={20} />}
              color="teal"
              label={t("dashboard.cards.total_products", { defaultValue: "Jami mahsulotlar" })}
              value={productsQuery.data?.total}
              loading={productsQuery.isLoading}
              error={productsQuery.isError ? (productsQuery.error instanceof Error ? productsQuery.error.message : t("errors.unknown", { defaultValue: "Xato" })) : null}
            />
          </Grid.Col>
        </Can>

        <Can permission="rbac:view">
          <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
            <StatCard
              icon={<IconUsers size={20} />}
              color="violet"
              label={t("dashboard.cards.total_users", { defaultValue: "Jami foydalanuvchilar" })}
              value={usersQuery.data?.total}
              loading={usersQuery.isLoading}
              error={usersQuery.isError ? (usersQuery.error instanceof Error ? usersQuery.error.message : t("errors.unknown", { defaultValue: "Xato" })) : null}
            />
          </Grid.Col>
        </Can>

        <Can permission="stats:view">
          <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
            <StatCard
              icon={<IconShoppingCart size={20} />}
              color="orange"
              label={t("dashboard.cards.sales", { defaultValue: "Savdo" })}
              value={salesQuery.data ? String(salesQuery.data.total_orders) : undefined}
              sub={salesQuery.data ? `${formatAmount(salesQuery.data.total_amount)} ${salesQuery.data.currency}` : undefined}
              loading={salesQuery.isLoading}
              error={salesQuery.isError ? (salesQuery.error instanceof Error ? salesQuery.error.message : t("errors.unknown", { defaultValue: "Xato" })) : null}
            />
          </Grid.Col>
        </Can>

        <Can permission="finance:view">
          <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
            <StatCard
              icon={<IconCash size={20} />}
              color={financeQuery.data ? (parseFloat(financeQuery.data.net_balance) >= 0 ? "green" : "red") : "gray"}
              label={t("dashboard.cards.net_balance", { defaultValue: "Sof balans" })}
              value={financeQuery.data ? `${formatAmount(financeQuery.data.net_balance)} UZS` : undefined}
              sub={financeQuery.data ? (parseFloat(financeQuery.data.net_balance) >= 0 ? t("stats.finance.creditor", { defaultValue: "Kreditor" }) : t("stats.finance.debtor", { defaultValue: "Debitor" })) : undefined}
              loading={financeQuery.isLoading}
              error={financeQuery.isError ? (financeQuery.error instanceof Error ? financeQuery.error.message : t("errors.unknown", { defaultValue: "Xato" })) : null}
            />
          </Grid.Col>
        </Can>
      </Grid>

      {/* Tezkor havolalar */}
      <Box>
        <Text fw={600} mb="sm" size="sm" c="dimmed">
          {t("dashboard.quick_links", { defaultValue: "Tezkor havolalar" })}
        </Text>
        <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="sm">
          <Can permission="analytics:view">
            <QuickLinkCard
              icon={<IconBrain size={18} />}
              color="indigo"
              label={t("nav.analytics", { defaultValue: "AI Tahlil" })}
              description={t("dashboard.admin.analytics_hint", { defaultValue: "Savdo trendy, prognoz" })}
              to="/analytics"
            />
          </Can>
          <Can permission="import:create">
            <QuickLinkCard
              icon={<IconFileImport size={18} />}
              color="cyan"
              label={t("nav.import", { defaultValue: "Import" })}
              description={t("dashboard.admin.import_hint", { defaultValue: "Excel, Nakladnoy" })}
              to="/import"
            />
          </Can>
          <Can permission="catalog:view">
            <QuickLinkCard
              icon={<IconShoppingBag size={18} />}
              color="grape"
              label={t("nav.marketplace", { defaultValue: "Marketplace" })}
              description={t("dashboard.admin.marketplace_hint", { defaultValue: "Do'konlar katalogi" })}
              to="/marketplace"
            />
          </Can>
          <Can permission="rbac:view">
            <QuickLinkCard
              icon={<IconUsers size={18} />}
              color="blue"
              label={t("nav.users", { defaultValue: "Foydalanuvchilar" })}
              description={t("dashboard.admin.users_hint", { defaultValue: "Boshqarish" })}
              to="/users"
            />
          </Can>
          <Can permission="stats:view">
            <QuickLinkCard
              icon={<IconChartBar size={18} />}
              color="orange"
              label={t("nav.stats", { defaultValue: "Statistika" })}
              description={t("dashboard.admin.stats_hint", { defaultValue: "Savdo, yetkazish" })}
              to="/stats"
            />
          </Can>
        </SimpleGrid>
      </Box>
    </Box>
  );
}
