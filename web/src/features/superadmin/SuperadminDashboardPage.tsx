/**
 * SuperadminDashboardPage — superadmin bosh sahifasi.
 *
 * Stat kartalar:
 * - Jami korxonalar
 * - Faol korxonalar
 * - To'xtatilgan korxonalar
 * - Jami foydalanuvchilar
 * - 7 kunlik yangi korxonalar
 *
 * Ma'lumot: GET /superadmin/stats
 */

import {
  Box,
  Grid,
  Group,
  Loader,
  Paper,
  Skeleton,
  Stack,
  Text,
  Title,
  ThemeIcon,
} from "@mantine/core";
import {
  IconBuildingSkyscraper,
  IconCircleCheck,
  IconPlayerPause,
  IconUsers,
  IconTrendingUp,
} from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import { useSuperadminStats } from "./api/superadminApi";

// ─── Stat karta ───────────────────────────────────────────────────────────────

interface StatCardProps {
  label: string;
  value: number | undefined;
  color: string;
  icon: React.ReactNode;
  loading: boolean;
}

function StatCard({ label, value, color, icon, loading }: StatCardProps) {
  return (
    <Paper withBorder p="md" radius="md">
      <Group justify="space-between" wrap="nowrap">
        <Box>
          <Text size="xs" c="dimmed" tt="uppercase" fw={700} mb={4}>
            {label}
          </Text>
          {loading ? (
            <Skeleton height={32} width={80} radius="sm" />
          ) : (
            <Title order={2} c={color}>
              {value ?? 0}
            </Title>
          )}
        </Box>
        <ThemeIcon color={color} variant="light" size={48} radius="md">
          {icon}
        </ThemeIcon>
      </Group>
    </Paper>
  );
}

// ─── Komponent ────────────────────────────────────────────────────────────────

export function SuperadminDashboardPage() {
  const { t } = useTranslation();
  const { data, isLoading, isError, error } = useSuperadminStats();

  return (
    <Stack gap="md">
      <Title order={3}>{t("superadmin.dashboard.title")}</Title>

      {isError ? (
        <Box py="xl" ta="center">
          <Text c="red">
            {error instanceof Error ? error.message : t("errors.unknown")}
          </Text>
        </Box>
      ) : (
        <Grid gutter="md">
          <Grid.Col span={{ base: 12, xs: 6, md: 4 }}>
            <StatCard
              label={t("superadmin.dashboard.enterprises_total")}
              value={data?.enterprises_total}
              color="blue"
              icon={<IconBuildingSkyscraper size={24} />}
              loading={isLoading}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, xs: 6, md: 4 }}>
            <StatCard
              label={t("superadmin.dashboard.enterprises_active")}
              value={data?.enterprises_active}
              color="green"
              icon={<IconCircleCheck size={24} />}
              loading={isLoading}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, xs: 6, md: 4 }}>
            <StatCard
              label={t("superadmin.dashboard.enterprises_suspended")}
              value={data?.enterprises_suspended}
              color="orange"
              icon={<IconPlayerPause size={24} />}
              loading={isLoading}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, xs: 6, md: 4 }}>
            <StatCard
              label={t("superadmin.dashboard.users_total")}
              value={data?.users_total}
              color="violet"
              icon={<IconUsers size={24} />}
              loading={isLoading}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, xs: 6, md: 4 }}>
            <StatCard
              label={t("superadmin.dashboard.enterprises_new_7d")}
              value={data?.enterprises_new_7d}
              color="teal"
              icon={<IconTrendingUp size={24} />}
              loading={isLoading}
            />
          </Grid.Col>
        </Grid>
      )}

      {isLoading && (
        <Group justify="center" py="sm">
          <Loader size="xs" />
          <Text size="sm" c="dimmed">{t("common.loading")}</Text>
        </Group>
      )}
    </Stack>
  );
}
