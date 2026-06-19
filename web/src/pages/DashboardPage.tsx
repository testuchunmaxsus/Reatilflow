/**
 * DashboardPage — bosh sahifa (T8 da to'liq UI qo'shiladi).
 */

import { Box, Card, Grid, Text, Title } from "@mantine/core";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/auth/AuthContext";
import { usePermissions } from "@/rbac/usePermissions";
import { Can } from "@/rbac/Can";

export function DashboardPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { role } = usePermissions();

  return (
    <Box>
      <Title order={3} mb="md">
        {t("pages.dashboard.title")}
      </Title>

      <Text c="dimmed" mb="xl">
        {user ? t("common.welcome", { name: user.full_name }) : ""}
        {role && ` — ${t(`common.role.${role}`)}`}
      </Text>

      <Grid>
        <Can permission="catalog:view">
          <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
            <Card shadow="sm" padding="lg" radius="md" withBorder>
              <Text fw={500}>{t("pages.catalog.title")}</Text>
              <Text size="sm" c="dimmed" mt={4}>
                {t("common.coming_soon")}
              </Text>
            </Card>
          </Grid.Col>
        </Can>

        <Can permission="customers:view">
          <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
            <Card shadow="sm" padding="lg" radius="md" withBorder>
              <Text fw={500}>{t("pages.customers.title")}</Text>
              <Text size="sm" c="dimmed" mt={4}>
                {t("common.coming_soon")}
              </Text>
            </Card>
          </Grid.Col>
        </Can>

        <Can permission="stats:view">
          <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
            <Card shadow="sm" padding="lg" radius="md" withBorder>
              <Text fw={500}>{t("pages.stats.title")}</Text>
              <Text size="sm" c="dimmed" mt={4}>
                {t("common.coming_soon")}
              </Text>
            </Card>
          </Grid.Col>
        </Can>
      </Grid>
    </Box>
  );
}
