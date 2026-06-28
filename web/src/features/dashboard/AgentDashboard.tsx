/**
 * AgentDashboard — agent bosh sahifasi.
 *
 * Widgetlar:
 *   - Mening do'konlarim     (customers:view) → useStores
 *   - Mening shartnomalarim  (contracts:view) → useContracts
 *   - Bugungi davomat holati (attendance:view) → useAttendanceList
 *   - Mening buyurtmalarim   (catalog:view)   → useOrders (agent_id filter)
 * Tezkor havolalar: /customers, /contracts, /attendance, /marketplace/browse, /gps, /agent-cabinet
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
  IconBuildingStore,
  IconFileText,
  IconCalendarStats,
  IconShoppingCart,
  IconMapPin,
  IconBriefcase,
  IconShoppingBag,
} from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/auth/AuthContext";
import { usePermissions } from "@/rbac/usePermissions";
import { Can } from "@/rbac/Can";
import { useStores } from "@/features/customers/api/customersApi";
import { useContracts } from "@/features/contracts/api/contractsApi";
import { useAttendanceList } from "@/api/attendanceApi";
import { useOrders } from "@/features/orders/api/ordersApi";
import { StatCard } from "./components/StatCard";
import { QuickLinkCard } from "./components/QuickLinkCard";

// Bugungi sana "YYYY-MM-DD" formatda
function todayStr(): string {
  return new Date().toISOString().slice(0, 10);
}

// Davomat holatini hisoblash
function getAttendanceStatus(
  items: { check_in_at: string; check_out_at: string | null; work_date: string }[],
  today: string,
  t: (key: string, opts?: { defaultValue: string }) => string
): { label: string; color: string } {
  const todayRecord = items.find((r) => r.work_date === today);
  if (!todayRecord) {
    return { label: t("dashboard.agent.attendance_none", { defaultValue: "Belgilanmagan" }), color: "gray" };
  }
  if (todayRecord.check_out_at) {
    return { label: t("dashboard.agent.attendance_done", { defaultValue: "Yakunlangan" }), color: "green" };
  }
  return { label: t("dashboard.agent.attendance_active", { defaultValue: "Ishda" }), color: "teal" };
}

export function AgentDashboard() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { role } = usePermissions();

  const today = todayStr();

  const storesQuery = useStores({ limit: 1 });
  const contractsQuery = useContracts({ limit: 1 });
  const attendanceQuery = useAttendanceList({
    user_id: user?.id,
    date: today,
    limit: 5,
  });
  const ordersQuery = useOrders({ agent_id: user?.id, limit: 1 });

  const attendance =
    attendanceQuery.data?.items
      ? getAttendanceStatus(attendanceQuery.data.items, today, t)
      : null;

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
        {/* Mening do'konlarim */}
        <Can permission="customers:view">
          <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
            <StatCard
              icon={<IconBuildingStore size={20} />}
              color="blue"
              label={t("dashboard.agent.my_stores", { defaultValue: "Mening do'konlarim" })}
              value={storesQuery.data?.total}
              loading={storesQuery.isLoading}
              error={
                storesQuery.isError
                  ? storesQuery.error instanceof Error
                    ? storesQuery.error.message
                    : t("errors.unknown", { defaultValue: "Xato" })
                  : null
              }
            />
          </Grid.Col>
        </Can>

        {/* Mening shartnomalarim */}
        <Can permission="contracts:view">
          <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
            <StatCard
              icon={<IconFileText size={20} />}
              color="teal"
              label={t("dashboard.agent.my_contracts", { defaultValue: "Mening shartnomalarim" })}
              value={contractsQuery.data?.total}
              loading={contractsQuery.isLoading}
              error={
                contractsQuery.isError
                  ? contractsQuery.error instanceof Error
                    ? contractsQuery.error.message
                    : t("errors.unknown", { defaultValue: "Xato" })
                  : null
              }
            />
          </Grid.Col>
        </Can>

        {/* Bugungi davomat holati */}
        <Can permission="attendance:view">
          <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
            <Box
              style={{
                border: "1px solid var(--mantine-color-default-border)",
                borderRadius: "var(--mantine-radius-md)",
                padding: "var(--mantine-spacing-lg)",
                height: "100%",
              }}
            >
              <Box mb="xs">
                <Text fw={500} size="sm" c="dimmed">
                  {t("dashboard.agent.attendance_today", { defaultValue: "Bugungi davomat" })}
                </Text>
              </Box>
              {attendanceQuery.isLoading ? (
                <Text size="sm" c="dimmed">...</Text>
              ) : attendanceQuery.isError ? (
                <Text size="sm" c="red">
                  {attendanceQuery.error instanceof Error
                    ? attendanceQuery.error.message
                    : t("errors.unknown", { defaultValue: "Xato" })}
                </Text>
              ) : attendance ? (
                <Badge color={attendance.color} variant="light" size="lg" mt={4}>
                  {attendance.label}
                </Badge>
              ) : (
                <Badge color="gray" variant="light" size="lg" mt={4}>
                  {t("dashboard.agent.attendance_none", { defaultValue: "Belgilanmagan" })}
                </Badge>
              )}
            </Box>
          </Grid.Col>
        </Can>

        {/* Mening buyurtmalarim */}
        <Can permission="catalog:view">
          <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
            <StatCard
              icon={<IconShoppingCart size={20} />}
              color="orange"
              label={t("dashboard.agent.my_orders", { defaultValue: "Mening buyurtmalarim" })}
              value={ordersQuery.data?.total}
              loading={ordersQuery.isLoading}
              error={
                ordersQuery.isError
                  ? ordersQuery.error instanceof Error
                    ? ordersQuery.error.message
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
        <SimpleGrid cols={{ base: 2, sm: 3 }} spacing="sm">
          <Can permission="customers:view">
            <QuickLinkCard
              icon={<IconBuildingStore size={18} />}
              color="blue"
              label={t("nav.customers", { defaultValue: "Do'konlar" })}
              description={t("dashboard.agent.customers_hint", { defaultValue: "Mijoz bazasi" })}
              to="/customers"
            />
          </Can>
          <Can permission="contracts:view">
            <QuickLinkCard
              icon={<IconFileText size={18} />}
              color="teal"
              label={t("nav.contracts", { defaultValue: "Shartnomalar" })}
              description={t("dashboard.agent.contracts_hint", { defaultValue: "Yangi shartnoma" })}
              to="/contracts"
            />
          </Can>
          <Can permission="attendance:view">
            <QuickLinkCard
              icon={<IconCalendarStats size={18} />}
              color="violet"
              label={t("nav.attendance", { defaultValue: "Davomat" })}
              description={t("dashboard.agent.attendance_hint", { defaultValue: "Kiriш/chiqish" })}
              to="/attendance"
            />
          </Can>
          <Can permission="catalog:view">
            <QuickLinkCard
              icon={<IconShoppingBag size={18} />}
              color="grape"
              label={t("dashboard.agent.marketplace_browse", { defaultValue: "Katalogdan buyurtma" })}
              description={t("dashboard.agent.marketplace_hint", { defaultValue: "Bir martalik buyurtma" })}
              to="/marketplace/browse"
            />
          </Can>
          <Can permission="gps:view">
            <QuickLinkCard
              icon={<IconMapPin size={18} />}
              color="red"
              label={t("nav.gps", { defaultValue: "GPS" })}
              description={t("dashboard.agent.gps_hint", { defaultValue: "Xarita, marshrut" })}
              to="/gps"
            />
          </Can>
          <Can permission="agent_cabinet:view">
            <QuickLinkCard
              icon={<IconBriefcase size={18} />}
              color="orange"
              label={t("nav.agent_cabinet", { defaultValue: "Agent kabineti" })}
              description={t("dashboard.agent.cabinet_hint", { defaultValue: "Shaxsiy statistika" })}
              to="/agent-cabinet"
            />
          </Can>
        </SimpleGrid>
      </Box>
    </Box>
  );
}
