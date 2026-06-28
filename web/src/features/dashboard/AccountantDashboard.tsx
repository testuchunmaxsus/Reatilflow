/**
 * AccountantDashboard — buxgalter bosh sahifasi.
 *
 * Widgetlar:
 *   - Sof balans / kirim / chiqim  (finance:view) → useFinanceStats
 *   - Jami ledger yozuvlari        (finance:view) → useLedger
 *   - POS bugungi savdo            (pos:view)     → usePosSummary
 *   - Savdo statistikasi           (stats:view)   → useSalesStats
 * Tezkor havolalar: /finance, /analytics, /pos, /import
 */

import {
  Box,
  Grid,
  SimpleGrid,
  Text,
  Title,
} from "@mantine/core";
import {
  IconCash,
  IconArrowUp,
  IconArrowDown,
  IconFileText,
  IconReceipt,
  IconShoppingCart,
  IconBrain,
  IconFileImport,
} from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/auth/AuthContext";
import { usePermissions } from "@/rbac/usePermissions";
import { Can } from "@/rbac/Can";
import { useFinanceStats } from "@/features/stats/api/statsApi";
import { useLedger } from "@/features/finance/api/financeApi";
import { usePosSummary } from "@/features/pos/api/posApi";
import { useSalesStats } from "@/features/stats/api/statsApi";
import { StatCard, formatAmount } from "./components/StatCard";
import { QuickLinkCard } from "./components/QuickLinkCard";

// Bugungi sana "YYYY-MM-DD" formatda
function todayStr(): string {
  return new Date().toISOString().slice(0, 10);
}

export function AccountantDashboard() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { role, can } = usePermissions();

  const financeQuery = useFinanceStats({}, can("finance:view"));
  const ledgerQuery = useLedger({ limit: 1 });
  const posQuery = usePosSummary(todayStr());
  const salesQuery = useSalesStats();

  return (
    <Box>
      <Title order={3} mb="xs">
        {t("pages.dashboard.title", { defaultValue: "Bosh sahifa" })}
      </Title>
      <Text c="dimmed" mb="xl">
        {user
          ? t("common.welcome", { name: user.full_name, defaultValue: `Xush kelibsiz, ${user.full_name}` })
          : ""}
        {role && ` — ${t(`common.role.${role}`, { defaultValue: role })}`}
      </Text>

      {/* KPI kartalar */}
      <Grid gutter="md" mb="xl">
        {/* Sof balans */}
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
              label={t("dashboard.cards.net_balance", { defaultValue: "Sof balans" })}
              value={
                financeQuery.data
                  ? `${formatAmount(financeQuery.data.net_balance)} UZS`
                  : undefined
              }
              sub={
                financeQuery.data
                  ? parseFloat(financeQuery.data.net_balance) >= 0
                    ? t("stats.finance.creditor", { defaultValue: "Kreditor" })
                    : t("stats.finance.debtor", { defaultValue: "Debitor" })
                  : undefined
              }
              loading={financeQuery.isLoading}
              error={
                financeQuery.isError
                  ? financeQuery.error instanceof Error
                    ? financeQuery.error.message
                    : t("errors.unknown", { defaultValue: "Xato" })
                  : null
              }
            />
          </Grid.Col>
        </Can>

        {/* Jami kirim */}
        <Can permission="finance:view">
          <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
            <StatCard
              icon={<IconArrowUp size={20} />}
              color="green"
              label={t("dashboard.accountant.total_debit", { defaultValue: "Jami kirim" })}
              value={
                financeQuery.data
                  ? `${formatAmount(financeQuery.data.total_debit)} UZS`
                  : undefined
              }
              loading={financeQuery.isLoading}
              error={
                financeQuery.isError
                  ? financeQuery.error instanceof Error
                    ? financeQuery.error.message
                    : t("errors.unknown", { defaultValue: "Xato" })
                  : null
              }
            />
          </Grid.Col>
        </Can>

        {/* Jami chiqim */}
        <Can permission="finance:view">
          <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
            <StatCard
              icon={<IconArrowDown size={20} />}
              color="red"
              label={t("dashboard.accountant.total_credit", { defaultValue: "Jami chiqim" })}
              value={
                financeQuery.data
                  ? `${formatAmount(financeQuery.data.total_credit)} UZS`
                  : undefined
              }
              loading={financeQuery.isLoading}
              error={
                financeQuery.isError
                  ? financeQuery.error instanceof Error
                    ? financeQuery.error.message
                    : t("errors.unknown", { defaultValue: "Xato" })
                  : null
              }
            />
          </Grid.Col>
        </Can>

        {/* Jami ledger yozuvlari (pending endpoint yo'q — jami ko'rsatiladi) */}
        <Can permission="finance:view">
          <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
            <StatCard
              icon={<IconFileText size={20} />}
              color="blue"
              label={t("dashboard.accountant.total_ledger", { defaultValue: "Jami moliyaviy yozuvlar" })}
              value={ledgerQuery.data?.total}
              loading={ledgerQuery.isLoading}
              error={
                ledgerQuery.isError
                  ? ledgerQuery.error instanceof Error
                    ? ledgerQuery.error.message
                    : t("errors.unknown", { defaultValue: "Xato" })
                  : null
              }
            />
          </Grid.Col>
        </Can>

        {/* POS bugungi savdo */}
        <Can permission="pos:view">
          <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
            <StatCard
              icon={<IconReceipt size={20} />}
              color="teal"
              label={t("dashboard.accountant.pos_today", { defaultValue: "POS bugungi savdo" })}
              value={posQuery.data ? String(posQuery.data.total_sales) : undefined}
              sub={
                posQuery.data
                  ? `${formatAmount(posQuery.data.total_amount)} UZS`
                  : undefined
              }
              loading={posQuery.isLoading}
              error={
                posQuery.isError
                  ? posQuery.error instanceof Error
                    ? posQuery.error.message
                    : t("errors.unknown", { defaultValue: "Xato" })
                  : null
              }
            />
          </Grid.Col>
        </Can>

        {/* Savdo buyurtmalari soni */}
        <Can permission="stats:view">
          <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
            <StatCard
              icon={<IconShoppingCart size={20} />}
              color="orange"
              label={t("dashboard.cards.sales", { defaultValue: "Savdo buyurtmalari" })}
              value={salesQuery.data ? String(salesQuery.data.total_orders) : undefined}
              sub={
                salesQuery.data
                  ? `${formatAmount(salesQuery.data.total_amount)} ${salesQuery.data.currency}`
                  : undefined
              }
              loading={salesQuery.isLoading}
              error={
                salesQuery.isError
                  ? salesQuery.error instanceof Error
                    ? salesQuery.error.message
                    : t("errors.unknown", { defaultValue: "Xato" })
                  : null
              }
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
          <Can permission="finance:view">
            <QuickLinkCard
              icon={<IconCash size={18} />}
              color="green"
              label={t("nav.finance", { defaultValue: "Moliya" })}
              description={t("dashboard.accountant.finance_hint", { defaultValue: "Ledger, balans" })}
              to="/finance"
            />
          </Can>
          <Can permission="analytics:view">
            <QuickLinkCard
              icon={<IconBrain size={18} />}
              color="indigo"
              label={t("nav.analytics", { defaultValue: "AI Tahlil" })}
              description={t("dashboard.accountant.analytics_hint", { defaultValue: "Savdo tahlili" })}
              to="/analytics"
            />
          </Can>
          <Can permission="pos:view">
            <QuickLinkCard
              icon={<IconReceipt size={18} />}
              color="teal"
              label={t("nav.pos", { defaultValue: "POS" })}
              description={t("dashboard.accountant.pos_hint", { defaultValue: "Kassir savdolari" })}
              to="/pos"
            />
          </Can>
          <Can permission="import:create">
            <QuickLinkCard
              icon={<IconFileImport size={18} />}
              color="cyan"
              label={t("nav.import", { defaultValue: "Import" })}
              description={t("dashboard.accountant.import_hint", { defaultValue: "Excel import" })}
              to="/import"
            />
          </Can>
        </SimpleGrid>
      </Box>
    </Box>
  );
}
