/**
 * AssignStoreModal — agent foydalanuvchisiga do'konlarni biriktirish modal.
 *
 * Xom UUID kiritmaydi — mavjud do'konlar ro'yxatidan Select bilan tanlanadi.
 * Bu T8'dagi xom-UUID kamchiligini yopadi.
 *
 * Backend: POST /customers/stores/{storeId}/assign-agent { agent_id }
 * Do'konlar: GET /customers/stores?limit=200
 */

import {
  Button,
  Group,
  Loader,
  Modal,
  Select,
  Stack,
  Text,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useTranslation } from "react-i18next";
import { useAssignAgentToStore, useStoreOptions } from "../api/usersApi";
import { useApiError } from "@/hooks/useApiError";
import type { UserOut } from "../types";

// ─── Props ────────────────────────────────────────────────────────────────────

interface AssignStoreModalProps {
  opened: boolean;
  onClose: () => void;
  user: UserOut | null;
}

// ─── Forma ────────────────────────────────────────────────────────────────────

interface AssignStoreFormValues {
  store_id: string;
}

// ─── Komponent ────────────────────────────────────────────────────────────────

export function AssignStoreModal({
  opened,
  onClose,
  user,
}: AssignStoreModalProps) {
  const { t } = useTranslation();
  const { showError, showSuccess } = useApiError();

  const { data: storesData, isLoading: storesLoading } = useStoreOptions();
  const assignAgent = useAssignAgentToStore();

  const storeOptions =
    storesData?.items.map((s) => ({
      value: s.id,
      label: s.name,
    })) ?? [];

  const form = useForm<AssignStoreFormValues>({
    initialValues: { store_id: "" },
    validate: {
      store_id: (v) =>
        !v ? t("users.assign_store.store_required") : null,
    },
  });

  const handleClose = () => {
    form.reset();
    onClose();
  };

  const handleSubmit = async (values: AssignStoreFormValues) => {
    if (!user) return;
    try {
      await assignAgent.mutateAsync({
        storeId: values.store_id,
        agentId: user.id,
      });
      showSuccess("users.assign_store.success");
      handleClose();
    } catch (err) {
      showError(err);
    }
  };

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={<Text fw={600}>{t("users.assign_store.title")}</Text>}
      size="sm"
      centered
    >
      {user && (
        <Text size="sm" c="dimmed" mb="md">
          {t("users.assign_store.agent_label")}:{" "}
          <strong>{user.full_name}</strong>
        </Text>
      )}

      <form onSubmit={form.onSubmit((v) => { void handleSubmit(v); })}>
        <Stack gap="sm">
          {storesLoading ? (
            <Group justify="center" py="sm">
              <Loader size="sm" />
              <Text size="sm" c="dimmed">
                {t("common.loading")}
              </Text>
            </Group>
          ) : (
            <Select
              label={t("users.assign_store.store_label")}
              placeholder={t("users.assign_store.store_placeholder")}
              data={storeOptions}
              searchable
              required
              nothingFoundMessage={t("users.assign_store.no_stores")}
              {...form.getInputProps("store_id")}
            />
          )}

          <Group justify="flex-end" mt="sm">
            <Button
              variant="subtle"
              onClick={handleClose}
              disabled={assignAgent.isPending}
            >
              {t("common.cancel")}
            </Button>
            <Button
              type="submit"
              loading={assignAgent.isPending}
              disabled={storesLoading}
            >
              {t("users.assign_store.submit")}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
