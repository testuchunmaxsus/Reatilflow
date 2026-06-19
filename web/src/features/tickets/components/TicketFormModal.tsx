/**
 * TicketFormModal — yangi murojaat yaratish modal.
 *
 * Maydonlar: ticket_type, subject, body, store_id (ixtiyoriy).
 * RBAC: barcha rollar (admin, agent, store, courier) yarata oladi.
 * i18n uz/ru.
 */

import {
  Button,
  Group,
  Modal,
  Select,
  Stack,
  Text,
  TextInput,
  Textarea,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useTranslation } from "react-i18next";
import { useCreateTicket } from "../api/ticketsApi";
import { useApiError } from "@/hooks/useApiError";
import type { TicketType } from "../types";

// ─── Props ────────────────────────────────────────────────────────────────────

interface TicketFormModalProps {
  opened: boolean;
  onClose: () => void;
}

// ─── Forma qiymatlari ─────────────────────────────────────────────────────────

interface TicketFormValues {
  ticket_type: TicketType | "";
  subject: string;
  body: string;
  store_id: string;
}

// ─── Komponent ────────────────────────────────────────────────────────────────

export function TicketFormModal({ opened, onClose }: TicketFormModalProps) {
  const { t } = useTranslation();
  const { showError, showSuccess } = useApiError();
  const createTicket = useCreateTicket();

  const ticketTypeOptions = [
    { value: "taklif", label: t("tickets.type.taklif") },
    { value: "etiroz", label: t("tickets.type.etiroz") },
  ];

  const form = useForm<TicketFormValues>({
    initialValues: {
      ticket_type: "",
      subject: "",
      body: "",
      store_id: "",
    },
    validate: {
      ticket_type: (v) =>
        !v ? t("tickets.form.type_required") : null,
      subject: (v) =>
        !v.trim() ? t("tickets.form.subject_required") : null,
      body: (v) =>
        !v.trim() ? t("tickets.form.body_required") : null,
    },
  });

  const handleClose = () => {
    form.reset();
    onClose();
  };

  const handleSubmit = async (values: TicketFormValues) => {
    try {
      await createTicket.mutateAsync({
        ticket_type: values.ticket_type as TicketType,
        subject: values.subject,
        body: values.body,
        store_id: values.store_id || null,
      });
      showSuccess("tickets.messages.created");
      handleClose();
    } catch (err) {
      showError(err);
    }
  };

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={
        <Text fw={600}>{t("tickets.form.create_title")}</Text>
      }
      size="md"
      centered
    >
      <form onSubmit={form.onSubmit((v) => { void handleSubmit(v); })}>
        <Stack gap="sm">
          <Select
            label={t("tickets.form.type")}
            placeholder={t("tickets.form.type_placeholder")}
            data={ticketTypeOptions}
            required
            {...form.getInputProps("ticket_type")}
          />

          <TextInput
            label={t("tickets.form.subject")}
            placeholder={t("tickets.form.subject_placeholder")}
            required
            {...form.getInputProps("subject")}
          />

          <Textarea
            label={t("tickets.form.body")}
            placeholder={t("tickets.form.body_placeholder")}
            minRows={3}
            required
            {...form.getInputProps("body")}
          />

          <TextInput
            label={t("tickets.form.store_id")}
            placeholder="UUID (ixtiyoriy)"
            description={t("tickets.form.store_id_hint")}
            {...form.getInputProps("store_id")}
          />

          <Group justify="flex-end" mt="md">
            <Button
              variant="subtle"
              onClick={handleClose}
              disabled={createTicket.isPending}
            >
              {t("common.cancel")}
            </Button>
            <Button type="submit" loading={createTicket.isPending}>
              {t("common.create")}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
