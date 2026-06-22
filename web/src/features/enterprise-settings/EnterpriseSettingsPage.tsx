/**
 * EnterpriseSettingsPage — korxona-admin o'z modullarini boshqaradi.
 *
 * Xususiyatlar:
 * - /enterprise/me dan joriy enabled_modules oladi
 * - Checkbox ro'yxati: administrator yoqadi/o'chiradi
 * - PATCH /enterprise/me/modules bilan saqlash
 * - Faqat 'administrator' roli (RBAC: rbac:view)
 * - i18n uz/ru
 */

import {
  Box,
  Button,
  Checkbox,
  Group,
  Loader,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { notifications } from "@mantine/notifications";
import { Can } from "@/rbac/Can";
import { useEnterprise } from "@/enterprise/EnterpriseContext";
import { apiClient } from "@/api/client";
import { useApiError } from "@/hooks/useApiError";
import { ALL_MODULE_KEYS_FRONTEND } from "@/features/superadmin/constants";
import type { EnterpriseInfo } from "@/enterprise/EnterpriseContext";

export function EnterpriseSettingsPage() {
  const { t } = useTranslation();
  const { enterprise, isLoading: entLoading, refreshEnterprise } = useEnterprise();
  const { showError } = useApiError();

  const [selectedModules, setSelectedModules] = useState<string[]>([]);
  const [isSaving, setIsSaving] = useState(false);

  // enterprise o'zgarganda state yangilash
  useEffect(() => {
    if (enterprise) {
      setSelectedModules([...enterprise.enabled_modules]);
    }
  }, [enterprise]);

  const handleToggle = (key: string, checked: boolean) => {
    setSelectedModules((prev) =>
      checked ? [...prev, key] : prev.filter((m) => m !== key),
    );
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await apiClient.patch<EnterpriseInfo>("/enterprise/me/modules", {
        enabled_modules: selectedModules,
      });
      await refreshEnterprise();
      notifications.show({
        color: "green",
        message: t("enterprise_settings.messages.saved"),
      });
    } catch (err) {
      showError(err);
    } finally {
      setIsSaving(false);
    }
  };

  const hasChanges =
    enterprise &&
    JSON.stringify([...selectedModules].sort()) !==
      JSON.stringify([...enterprise.enabled_modules].sort());

  return (
    <Can
      permission="rbac:view"
      fallback={
        <Box py="xl" ta="center">
          <Text c="dimmed">{t("users.access_denied")}</Text>
        </Box>
      }
    >
      <Stack gap="md">
        <Title order={3}>{t("nav.settings")}</Title>
        <Text c="dimmed" size="sm">
          {t("enterprise_settings.description")}
        </Text>

        {entLoading ? (
          <Group justify="center" py="xl">
            <Loader />
          </Group>
        ) : !enterprise ? (
          <Box py="xl" ta="center">
            <Text c="dimmed">{t("enterprise_settings.no_enterprise")}</Text>
          </Box>
        ) : (
          <Stack gap="lg">
            <Box>
              <Text size="sm" fw={500} mb="xs">
                {t("enterprise_settings.modules_label")}
              </Text>
              <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} spacing="xs">
                {ALL_MODULE_KEYS_FRONTEND.map((key) => (
                  <Checkbox
                    key={key}
                    label={t(`superadmin.modules.${key}`, { defaultValue: key })}
                    checked={selectedModules.includes(key)}
                    onChange={(e) => handleToggle(key, e.currentTarget.checked)}
                  />
                ))}
              </SimpleGrid>
            </Box>

            <Group>
              <Button
                onClick={() => { void handleSave(); }}
                loading={isSaving}
                disabled={!hasChanges}
              >
                {t("common.save")}
              </Button>
              {hasChanges && (
                <Button
                  variant="default"
                  disabled={isSaving}
                  onClick={() => {
                    if (enterprise) setSelectedModules([...enterprise.enabled_modules]);
                  }}
                >
                  {t("common.cancel")}
                </Button>
              )}
            </Group>
          </Stack>
        )}
      </Stack>
    </Can>
  );
}
