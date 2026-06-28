/**
 * StoreDashboard — do'kon bosh sahifasi.
 *
 * Widgetlar:
 *   - Bugungi POS savdo        (pos:view)      → usePosSummary
 *   - Chiquvchi buyurtmalar    (catalog:view)  → useOutgoingOrders
 *   - Muddati o'tayotgan tovar (pos:view)      → usePosInventory (client-side filter)
 *   - Mening balansim          (finance:view)  → useBalance (branch_id bo'lsa)
 * Tezkor havolalar: /marketplace/browse, /pos/sell, /orders, /finance
 *
 * Eslatma: store_id = user.branch_id (agar null bo'lsa balans yashiriladi)
 */

import {
  Badge,
  Box,
  Grid,
  SimpleGrid,
  Text,
  Title,
} from "@mantine/core";
import {
  IconReceipt,
  IconShoppingBag,
  IconAlertTriangle,
  IconCash,
  IconShoppingCart,
} from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/auth/AuthContext";
import { usePermissions } from "@/rbac/usePermissions";
import { Can } from "@/rbac/Can";
import { usePosSummary, usePosInventory } from "@/features/pos/api/posApi";
import { useOutgoingOrders } from "@/features/marketplace/api/marketplaceApi";
import { useBalance } from "@/features/finance/api/financeApi";
import { StatCard, formatAmount } from "./components/StatCard";
import { QuickLinkCard } from "./components/QuickLinkCard";

// Bugungi sana "YYYY-MM-DD" formatda
function todayStr(): string {
  return new Date().toISOString().slice(0, 10);
}

// Kam qolgan tovar — client-side heuristika (ostona: qty < 5 yoki muddati o'tayotgan)
const LOW_STOCK_THRESHOLD = 5;

export function StoreDashboard() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { role, can } = usePermissions();

  const storeId = user?.branch_id ?? "";
  const hasStoreId = Boolean(storeId);

  const posQuery = usePosSummary(todayStr(), storeId || undefined);
  const outgoingQuery = useOutgoingOrders({ limit: 1 });
  const inventoryQuery = usePosInventory({
    store_id: storeId || undefined,
    limit: 50,
  });
  const balanceQuery = useBalance(storeId, can("finance:view") && hasStoreId);

  // Muddati o'tayotgan yoki kam qolgan tovarlar soni
  const alertCount =
    inventoryQuery.data?.items.filter(
      (item) =>
        item.is_near_expiry ||
        item.is_expired ||
        parseFloat(item.qty) < LOW_STOCK_THRESHOLD
    ).length ?? 0;

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
        {/* Bugungi POS savdo */}
        <Can permission="pos:view">
          <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
            <StatCard
              icon={<IconReceipt size={20} />}
              color="teal"
              label={t("dashboard.store.pos_today", { defaultValue: "Bugungi savdo" })}
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

        {/* Chiquvchi buyurtmalar (marketplace) */}
        <Can permission="catalog:view">
          <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
            <StatCard
              icon={<IconShoppingCart size={20} />}
              color="orange"
              label={t("dashboard.store.outgoing_orders", { defaultValue: "Marketplace buyurtmalar" })}
              value={outgoingQuery.data?.total}
              loading={outgoingQuery.isLoading}
              error={
                outgoingQuery.isError
                  ? outgoingQuery.error instanceof Error
                    ? outgoingQuery.error.message
                    : t("errors.unknown", { defaultValue: "Xato" })
                  : null
              }
            />
          </Grid.Col>
        </Can>

        {/* Muddati o'tayotgan / kam qolgan tovar */}
        <Can permission="pos:view">
          <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
            <Box
              style={{
                border: `1px solid ${alertCount > 0 ? "var(--mantine-color-orange-4)" : "var(--mantine-color-default-border)"}`,
                borderRadius: "var(--mantine-radius-md)",
                padding: "var(--mantine-spacing-lg)",
                height: "100%",
              }}
            >
              <Box mb="xs">
                <Text fw={500} size="sm" c="dimmed">
                  {t("dashboard.store.alerts", { defaultValue: "Tovar ogohlantirishlari" })}
                </Text>
              </Box>
              {inventoryQuery.isLoading ? (
                <Text size="sm" c="dimmed">...</Text>
              ) : inventoryQuery.isError ? (
                <Text size="sm" c="red">
                  {inventoryQuery.error instanceof Error
                    ? inventoryQuery.error.message
                    : t("errors.unknown", { defaultValue: "Xato" })}
                </Text>
              ) : (
                <Badge
                  color={alertCount > 0 ? "orange" : "green"}
                  variant="light"
                  size="lg"
                  leftSection={alertCount > 0 ? <IconAlertTriangle size={14} /> : undefined}
                  mt={4}
                >
                  {alertCount > 0
                    ? t("dashboard.store.alerts_count", {
                        defaultValue: `${alertCount} ta tovar`,
                        count: alertCount,
                      })
                    : t("dashboard.store.alerts_ok", { defaultValue: "Hammasi yaxshi" })}
                </Badge>
              )}
            </Box>
          </Grid.Col>
        </Can>

        {/* Mening balansim (faqat branch_id mavjud bo'lsa) */}
        {hasStoreId && (
          <Can permission="finance:view">
            <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
              <StatCard
                icon={<IconCash size={20} />}
                color={
                  balanceQuery.data
                    ? parseFloat(String(balanceQuery.data.balance)) >= 0
                      ? "green"
                      : "red"
                    : "gray"
                }
                label={t("dashboard.store.my_balance", { defaultValue: "Mening balansim" })}
                value={
                  balanceQuery.data
                    ? `${formatAmount(String(balanceQuery.data.balance))} UZS`
                    : undefined
                }
                loading={balanceQuery.isLoading}
                error={
                  balanceQuery.isError
                    ? balanceQuery.error instanceof Error
                      ? balanceQuery.error.message
                      : t("errors.unknown", { defaultValue: "Xato" })
                    : null
                }
              />
            </Grid.Col>
          </Can>
        )}
      </Grid>

      {/* Tezkor havolalar */}
      <Box>
        <Text fw={600} mb="sm" size="sm" c="dimmed">
          {t("dashboard.quick_links", { defaultValue: "Tezkor havolalar" })}
        </Text>
        <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="sm">
          <Can permission="catalog:view">
            <QuickLinkCard
              icon={<IconShoppingBag size={18} />}
              color="grape"
              label={t("dashboard.store.browse_catalog", { defaultValue: "Katalogdan buyurtma" })}
              description={t("dashboard.store.browse_hint", { defaultValue: "Marketplace do'konlari" })}
              to="/marketplace/browse"
            />
          </Can>
          <Can permission="pos:view">
            <QuickLinkCard
              icon={<IconReceipt size={18} />}
              color="teal"
              label={t("dashboard.store.pos_sell", { defaultValue: "POS kassir" })}
              description={t("dashboard.store.pos_hint", { defaultValue: "Yangi sotuv" })}
              to="/pos/sell"
            />
          </Can>
          <Can permission="catalog:view">
            <QuickLinkCard
              icon={<IconShoppingCart size={18} />}
              color="orange"
              label={t("nav.orders", { defaultValue: "Buyurtmalar" })}
              description={t("dashboard.store.orders_hint", { defaultValue: "Mening buyurtmalarim" })}
              to="/orders"
            />
          </Can>
          <Can permission="finance:view">
            <QuickLinkCard
              icon={<IconCash size={18} />}
              color="green"
              label={t("nav.finance", { defaultValue: "Moliya" })}
              description={t("dashboard.store.finance_hint", { defaultValue: "O'z balansi" })}
              to="/finance"
            />
          </Can>
        </SimpleGrid>
      </Box>
    </Box>
  );
}
