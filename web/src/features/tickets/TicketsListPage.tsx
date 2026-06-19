/**
 * TicketsListPage — murojaatlar boshqaruv sahifasi.
 *
 * Xususiyatlar:
 * - Paginated jadval — server-side
 * - Filtrlar: status, ticket_type
 * - RBAC scope: admin/accountant hammasini ko'radi; boshqalar o'zinikini
 * - Detail modal: xabarlar tarixi + yangi xabar + holat mashinasi
 * - Yangi murojaat yaratish modal
 * - <Can> mos ruxsatlar
 * - i18n uz/ru
 */

import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Group,
  Loader,
  Pagination,
  Select,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import { IconEye, IconPlus } from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useDisclosure } from "@mantine/hooks";
import { Can } from "@/rbac/Can";
import { useTickets } from "./api/ticketsApi";
import { TicketFormModal } from "./components/TicketFormModal";
import { TicketDetailModal } from "./components/TicketDetailModal";
import { useApiError } from "@/hooks/useApiError";
import type { TicketOut, TicketStatus, TicketType, TicketFilters } from "./types";

const PAGE_SIZE = 20;

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

// ─── Komponent ────────────────────────────────────────────────────────────────

export function TicketsListPage() {
  const { t } = useTranslation();
  const { showError: _showError } = useApiError();

  // Filtrlar
  const [statusFilter, setStatusFilter] = useState<TicketStatus | "">("");
  const [typeFilter, setTypeFilter] = useState<TicketType | "">("");
  const [page, setPage] = useState(1);
  const offset = (page - 1) * PAGE_SIZE;

  // Modal holatlari
  const [formOpened, { open: openForm, close: closeForm }] =
    useDisclosure(false);
  const [detailOpened, { open: openDetail, close: closeDetail }] =
    useDisclosure(false);
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);

  // Filtr params
  const filters: TicketFilters = {
    ...(statusFilter ? { status: statusFilter } : {}),
    ...(typeFilter ? { ticket_type: typeFilter } : {}),
    limit: PAGE_SIZE,
    offset,
  };

  const { data, isLoading, isError, error } = useTickets(filters);

  const handleViewClick = (ticket: TicketOut) => {
    setSelectedTicketId(ticket.id);
    openDetail();
  };

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1;

  const statusOptions = [
    { value: "", label: t("tickets.filter.all_statuses") },
    { value: "new", label: t("tickets.status.new") },
    { value: "in_progress", label: t("tickets.status.in_progress") },
    { value: "resolved", label: t("tickets.status.resolved") },
    { value: "closed", label: t("tickets.status.closed") },
  ];

  const typeOptions = [
    { value: "", label: t("tickets.filter.all_types") },
    { value: "taklif", label: t("tickets.type.taklif") },
    { value: "etiroz", label: t("tickets.type.etiroz") },
  ];

  return (
    <Can
      permission="tickets:view"
      fallback={
        <Box py="xl" ta="center">
          <Text c="dimmed">{t("tickets.access_denied")}</Text>
        </Box>
      }
    >
      <Stack gap="md">
        {/* Sarlavha va yaratish tugmasi */}
        <Group justify="space-between">
          <Title order={3}>{t("pages.tickets.title")}</Title>
          <Can permission="tickets:create">
            <Button
              leftSection={<IconPlus size={16} />}
              onClick={openForm}
            >
              {t("tickets.actions.create")}
            </Button>
          </Can>
        </Group>

        {/* Filtrlar */}
        <Group gap="sm" wrap="wrap">
          <Select
            data={statusOptions}
            value={statusFilter}
            onChange={(v) => {
              setStatusFilter((v ?? "") as TicketStatus | "");
              setPage(1);
            }}
            w={180}
            aria-label={t("tickets.filter.status")}
            allowDeselect={false}
          />
          <Select
            data={typeOptions}
            value={typeFilter}
            onChange={(v) => {
              setTypeFilter((v ?? "") as TicketType | "");
              setPage(1);
            }}
            w={160}
            aria-label={t("tickets.filter.type")}
            allowDeselect={false}
          />
        </Group>

        {/* Jadval */}
        {isLoading ? (
          <Group justify="center" py="xl">
            <Loader />
            <Text c="dimmed">{t("common.loading")}</Text>
          </Group>
        ) : isError ? (
          <Box py="xl" ta="center">
            <Text c="red">
              {error instanceof Error ? error.message : t("errors.unknown")}
            </Text>
          </Box>
        ) : !data?.items.length ? (
          <Box py="xl" ta="center">
            <Text c="dimmed">{t("tickets.table.empty")}</Text>
          </Box>
        ) : (
          <Table.ScrollContainer minWidth={900}>
            <Table striped highlightOnHover withTableBorder>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t("tickets.table.subject")}</Table.Th>
                  <Table.Th>{t("tickets.table.type")}</Table.Th>
                  <Table.Th>{t("tickets.table.status")}</Table.Th>
                  <Table.Th>{t("tickets.table.store_id")}</Table.Th>
                  <Table.Th>{t("tickets.table.created_at")}</Table.Th>
                  <Table.Th>{t("catalog.table.actions")}</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {data.items.map((ticket) => (
                  <Table.Tr key={ticket.id}>
                    <Table.Td>
                      <Text size="sm" fw={500} lineClamp={1}>
                        {ticket.subject}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Badge variant="outline" size="sm" color="blue">
                        {t(`tickets.type.${ticket.ticket_type}`)}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Badge
                        color={statusColor(ticket.status)}
                        variant="light"
                        size="sm"
                      >
                        {t(`tickets.status.${ticket.status}`)}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" c="dimmed" ff="monospace" lineClamp={1}>
                        {ticket.store_id ?? "—"}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" c="dimmed">
                        {new Date(ticket.created_at).toLocaleDateString(
                          "uz-UZ",
                        )}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Tooltip label={t("tickets.actions.view")}>
                        <ActionIcon
                          variant="subtle"
                          onClick={() => handleViewClick(ticket)}
                          aria-label={t("tickets.actions.view")}
                        >
                          <IconEye size={16} />
                        </ActionIcon>
                      </Tooltip>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <Group justify="center">
            <Pagination
              value={page}
              onChange={setPage}
              total={totalPages}
              size="sm"
            />
          </Group>
        )}

        {/* Modallar */}
        <TicketFormModal opened={formOpened} onClose={closeForm} />
        <TicketDetailModal
          opened={detailOpened}
          onClose={closeDetail}
          ticketId={selectedTicketId}
        />
      </Stack>
    </Can>
  );
}
