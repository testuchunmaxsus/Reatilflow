/**
 * AssignAgentModal — do'konga agent biriktirish modal (faqat administrator).
 *
 * POST /customers/stores/{id}/assign-agent
 * RBAC: customers:edit + admin check (backend ham tekshiradi).
 */

import {
  Button,
  Group,
  Modal,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { UuidHelp } from "@/components/UuidHelp";
import { useForm } from "@mantine/form";
import { useTranslation } from "react-i18next";
import { useAssignAgent } from "../api/customersApi";
import { useApiError } from "@/hooks/useApiError";
import type { StoreOut } from "@/api/types";

interface AssignAgentModalProps {
  opened: boolean;
  onClose: () => void;
  store: StoreOut | null;
}

interface AssignAgentFormValues {
  agent_id: string;
}

export function AssignAgentModal({
  opened,
  onClose,
  store,
}: AssignAgentModalProps) {
  const { t } = useTranslation();
  const { showError, showSuccess } = useApiError();
  const assignAgent = useAssignAgent();

  const form = useForm<AssignAgentFormValues>({
    initialValues: {
      agent_id: store?.agent_id ?? "",
    },
    validate: {
      agent_id: (v) =>
        v.trim().length === 0
          ? t("customers.assign_agent.agent_id_required")
          : null,
    },
  });

  const handleClose = () => {
    form.reset();
    onClose();
  };

  const handleSubmit = async (values: AssignAgentFormValues) => {
    if (!store) return;
    try {
      await assignAgent.mutateAsync({
        storeId: store.id,
        data: { agent_id: values.agent_id },
      });
      showSuccess("customers.messages.agent_assigned");
      handleClose();
    } catch (err) {
      showError(err);
    }
  };

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={<Text fw={600}>{t("customers.assign_agent.title")}</Text>}
      size="sm"
      centered
    >
      {store && (
        <Text size="sm" c="dimmed" mb="md">
          {t("customers.assign_agent.store_label")}: <strong>{store.name}</strong>
        </Text>
      )}
      <form onSubmit={form.onSubmit((v) => { void handleSubmit(v); })}>
        <Stack gap="sm">
          <TextInput
            label={
              <Group gap={4} component="span">
                {t("customers.assign_agent.agent_id_label")}
                <UuidHelp />
              </Group>
            }
            placeholder="UUID"
            description={t("customers.assign_agent.agent_id_hint")}
            required
            {...form.getInputProps("agent_id")}
          />
          <Group justify="flex-end" mt="sm">
            <Button
              variant="subtle"
              onClick={handleClose}
              disabled={assignAgent.isPending}
            >
              {t("common.cancel")}
            </Button>
            <Button type="submit" loading={assignAgent.isPending}>
              {t("customers.assign_agent.submit")}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
