/**
 * TicketDetailModal — murojaat tafsiloti, xabarlar tarixi va holat boshqaruvi.
 *
 * - Xabarlar tarixi (messages)
 * - Yangi xabar qo'shish
 * - Holat o'zgartirish (admin/accountant — <Can permission="tickets:edit">)
 * - Holat mashinasi: new → in_progress → resolved → closed; resolved → in_progress
 * - i18n uz/ru
 */

import {
  Badge,
  Box,
  Button,
  Divider,
  Group,
  Loader,
  Modal,
  Paper,
  ScrollArea,
  Select,
  Stack,
  Text,
  Textarea,
} from "@mantine/core";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { notifications } from "@mantine/notifications";
import { Can } from "@/rbac/Can";
import { useTicket, useAddTicketMessage, useUpdateTicketStatus } from "../api/ticketsApi";
import { useApiError } from "@/hooks/useApiError";
import type { TicketStatus } from "../types";

// ─── Holat mashinasi — backend ruxsat bergan o'tishlar ───────────────────────

function allowedTransitions(current: TicketStatus): TicketStatus[] {
  switch (current) {
    case "new":
      return ["in_progress"];
    case "in_progress":
      return ["resolved", "closed"];
    case "resolved":
      return ["in_progress", "closed"];
    case "closed":
      return [];
    default:
      return [];
  }
}

// ─── Status badge rangi ───────────────────────────────────────────────────────

function statusColor(s: TicketStatus): string {
  switch (s) {
    case "new":
      return "blue";
    case "in_progress":
      return "orange";
    case "resolved":
      return "green";
    case "closed":
      return "gray";
    default:
      return "gray";
  }
}

// ─── Props ────────────────────────────────────────────────────────────────────

interface TicketDetailModalProps {
  opened: boolean;
  onClose: () => void;
  ticketId: string | null;
}

// ─── Komponent ────────────────────────────────────────────────────────────────

export function TicketDetailModal({
  opened,
  onClose,
  ticketId,
}: TicketDetailModalProps) {
  const { t } = useTranslation();
  const { showError } = useApiError();

  const [messageBody, setMessageBody] = useState("");
  const [nextStatus, setNextStatus] = useState<TicketStatus | "">("");

  const { data: ticket, isLoading } = useTicket(
    ticketId ?? "",
    Boolean(ticketId && opened),
  );
  const addMessage = useAddTicketMessage();
  const updateStatus = useUpdateTicketStatus();

  const handleClose = () => {
    setMessageBody("");
    setNextStatus("");
    onClose();
  };

  const handleSendMessage = async () => {
    if (!ticketId || !messageBody.trim()) return;
    try {
      await addMessage.mutateAsync({
        ticketId,
        data: { body: messageBody.trim() },
      });
      setMessageBody("");
      notifications.show({
        color: "green",
        message: t("tickets.messages.message_added"),
      });
    } catch (err) {
      showError(err);
    }
  };

  const handleStatusChange = async () => {
    if (!ticketId || !ticket || !nextStatus) return;
    try {
      await updateStatus.mutateAsync({
        ticketId,
        data: { status: nextStatus, version: ticket.version },
      });
      setNextStatus("");
      notifications.show({
        color: "green",
        message: t("tickets.messages.status_updated", {
          status: t(`tickets.status.${nextStatus}`),
        }),
      });
    } catch (err) {
      showError(err);
    }
  };

  const transitions = ticket ? allowedTransitions(ticket.status) : [];
  const transitionOptions = transitions.map((s) => ({
    value: s,
    label: t(`tickets.status.${s}`),
  }));

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={
        <Text fw={600}>
          {ticket ? ticket.subject : t("tickets.detail.title")}
        </Text>
      }
      size="lg"
      centered
    >
      {isLoading ? (
        <Group justify="center" py="xl">
          <Loader />
          <Text c="dimmed">{t("common.loading")}</Text>
        </Group>
      ) : !ticket ? (
        <Text c="dimmed" ta="center" py="xl">
          {t("tickets.detail.not_found")}
        </Text>
      ) : (
        <Stack gap="md">
          {/* Murojaat meta */}
          <Group gap="xs">
            <Badge color={statusColor(ticket.status)} variant="light">
              {t(`tickets.status.${ticket.status}`)}
            </Badge>
            <Badge color="blue" variant="outline" size="sm">
              {t(`tickets.type.${ticket.ticket_type}`)}
            </Badge>
          </Group>

          <Text size="sm" c="dimmed">
            {ticket.body}
          </Text>

          <Divider label={t("tickets.detail.messages")} />

          {/* Xabarlar tarixi */}
          <ScrollArea h={240} offsetScrollbars>
            <Stack gap="xs">
              {!ticket.messages || ticket.messages.length === 0 ? (
                <Text size="sm" c="dimmed" ta="center">
                  {t("tickets.detail.no_messages")}
                </Text>
              ) : (
                ticket.messages.map((msg) => (
                  <Paper
                    key={msg.id}
                    withBorder
                    p="xs"
                    radius="sm"
                    bg="gray.0"
                  >
                    <Text size="xs" c="dimmed" mb={4}>
                      {new Date(msg.created_at).toLocaleString("uz-UZ")}
                    </Text>
                    <Text size="sm">{msg.body}</Text>
                    {msg.attachment_url && (
                      <Text size="xs" mt={4}>
                        <a
                          href={msg.attachment_url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {t("tickets.detail.attachment")}
                        </a>
                      </Text>
                    )}
                  </Paper>
                ))
              )}
            </Stack>
          </ScrollArea>

          {/* Yangi xabar */}
          <Divider label={t("tickets.detail.add_message")} />
          <Textarea
            placeholder={t("tickets.detail.message_placeholder")}
            value={messageBody}
            onChange={(e) => setMessageBody(e.currentTarget.value)}
            minRows={2}
            aria-label={t("tickets.detail.add_message")}
          />
          <Group justify="flex-end">
            <Button
              onClick={() => { void handleSendMessage(); }}
              disabled={!messageBody.trim()}
              loading={addMessage.isPending}
              size="sm"
            >
              {t("tickets.detail.send")}
            </Button>
          </Group>

          {/* Holat o'zgartirish — faqat admin/accountant */}
          {transitions.length > 0 && (
            <Can permission="tickets:edit">
              <Divider label={t("tickets.detail.change_status")} />
              <Group gap="sm">
                <Box flex={1}>
                  <Select
                    data={transitionOptions}
                    value={nextStatus}
                    onChange={(v) => setNextStatus((v ?? "") as TicketStatus | "")}
                    placeholder={t("tickets.detail.select_status")}
                    aria-label={t("tickets.detail.change_status")}
                    allowDeselect={false}
                  />
                </Box>
                <Button
                  onClick={() => { void handleStatusChange(); }}
                  disabled={!nextStatus}
                  loading={updateStatus.isPending}
                  size="sm"
                  color="blue"
                >
                  {t("tickets.detail.apply_status")}
                </Button>
              </Group>
            </Can>
          )}
        </Stack>
      )}
    </Modal>
  );
}
