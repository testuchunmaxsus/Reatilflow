/**
 * SuperadminAuditLogsPage — audit log sahifasi.
 *
 * Xususiyatlar:
 * - Jadval: vaqt (formatDate), action badge, entity_type, entity_id, korxona
 * - Filtrlar: action (Select), entity_type (Select), korxona (Select)
 * - Pagination (20 ta/sahifa)
 * - Before/after JSON ni modal orqali ko'rish
 */

import {
  ActionIcon,
  Badge,
  Box,
  Code,
  Group,
  Loader,
  Modal,
  Pagination,
  ScrollArea,
  Select,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { IconEye } from "@tabler/icons-react";
import { useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useAuditLogs } from "./api/superadminApi";
import { useEnterprises } from "./api/superadminApi";
import type { AuditLogOut } from "./types";
import { formatDate } from "@/utils/date";

const PAGE_SIZE = 20;

// ─── Action badge rangi ───────────────────────────────────────────────────────

function actionColor(action: string): string {
  if (action.startsWith("create")) return "green";
  if (action.startsWith("delete") || action.startsWith("remove")) return "red";
  if (action.startsWith("update") || action.startsWith("patch")) return "blue";
  if (action.startsWith("suspend")) return "orange";
  if (action.startsWith("activate")) return "teal";
  return "gray";
}

// ─── JSON ko'rish modali ──────────────────────────────────────────────────────

interface JsonViewModalProps {
  opened: boolean;
  onClose: () => void;
  log: AuditLogOut | null;
}

function JsonViewModal({ opened, onClose, log }: JsonViewModalProps) {
  const { t } = useTranslation();

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={
        <Text fw={600}>
          {t("superadmin.audit.json_modal_title")} — {log?.action ?? ""}
        </Text>
      }
      size="lg"
    >
      {log && (
        <Stack gap="md">
          {log.before_json && (
            <Box>
              <Text size="sm" fw={500} c="orange" mb={4}>
                {t("superadmin.audit.before")}
              </Text>
              <ScrollArea h={200}>
                <Code block>{JSON.stringify(log.before_json, null, 2)}</Code>
              </ScrollArea>
            </Box>
          )}
          {log.after_json && (
            <Box>
              <Text size="sm" fw={500} c="green" mb={4}>
                {t("superadmin.audit.after")}
              </Text>
              <ScrollArea h={200}>
                <Code block>{JSON.stringify(log.after_json, null, 2)}</Code>
              </ScrollArea>
            </Box>
          )}
          {!log.before_json && !log.after_json && (
            <Text c="dimmed" size="sm">
              {t("superadmin.audit.no_json")}
            </Text>
          )}
        </Stack>
      )}
    </Modal>
  );
}

// ─── Komponent ────────────────────────────────────────────────────────────────

export function SuperadminAuditLogsPage() {
  const { t } = useTranslation();

  const [page, setPage] = useState(1);
  const [actionFilter, setActionFilter] = useState("");
  const [entityTypeFilter, setEntityTypeFilter] = useState("");
  const [enterpriseFilter, setEnterpriseFilter] = useState("");

  const [jsonModalOpened, { open: openJsonModal, close: closeJsonModal }] =
    useDisclosure(false);
  const [selectedLog, setSelectedLog] = useState<AuditLogOut | null>(null);

  const offset = (page - 1) * PAGE_SIZE;

  const { data, isLoading, isError, error } = useAuditLogs({
    action: actionFilter,
    entity_type: entityTypeFilter,
    enterprise_id: enterpriseFilter,
    limit: PAGE_SIZE,
    offset,
  });

  // Korxonalar filtri uchun
  const { data: enterprisesData } = useEnterprises({ limit: 100, offset: 0 });

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1;

  const handleActionChange = useCallback((val: string | null) => {
    setActionFilter(val ?? "");
    setPage(1);
  }, []);

  const handleEntityTypeChange = useCallback((val: string | null) => {
    setEntityTypeFilter(val ?? "");
    setPage(1);
  }, []);

  const handleEnterpriseChange = useCallback((val: string | null) => {
    setEnterpriseFilter(val ?? "");
    setPage(1);
  }, []);

  const handleViewJson = (log: AuditLogOut) => {
    setSelectedLog(log);
    openJsonModal();
  };

  const enterpriseOptions = (enterprisesData?.items ?? []).map((ent) => ({
    value: ent.id,
    label: ent.name,
  }));

  // Keng tarqalgan amallar ro'yxati
  const actionOptions = [
    "create_enterprise",
    "update_enterprise",
    "delete_enterprise",
    "suspend_enterprise",
    "activate_enterprise",
    "create_user",
    "update_user",
    "delete_user",
    "create_product",
    "update_product",
    "delete_product",
    "create_order",
    "update_order",
    "banner_toggle",
    "banner_delete",
  ].map((a) => ({ value: a, label: a }));

  const entityTypeOptions = [
    "enterprise",
    "user",
    "product",
    "order",
    "banner",
    "promo",
    "contract",
    "ticket",
  ].map((e) => ({ value: e, label: e }));

  return (
    <Stack gap="md">
      {/* Sarlavha */}
      <Title order={3}>{t("superadmin.audit.title")}</Title>

      {/* Filtrlar */}
      <Group gap="sm" wrap="wrap">
        <Select
          placeholder={t("superadmin.audit.filter.all_actions")}
          value={actionFilter || null}
          onChange={handleActionChange}
          data={actionOptions}
          clearable
          searchable
          w={220}
          aria-label={t("superadmin.audit.filter.action")}
        />
        <Select
          placeholder={t("superadmin.audit.filter.all_entity_types")}
          value={entityTypeFilter || null}
          onChange={handleEntityTypeChange}
          data={entityTypeOptions}
          clearable
          searchable
          w={180}
          aria-label={t("superadmin.audit.filter.entity_type")}
        />
        <Select
          placeholder={t("superadmin.audit.filter.all_enterprises")}
          value={enterpriseFilter || null}
          onChange={handleEnterpriseChange}
          data={enterpriseOptions}
          clearable
          searchable
          w={220}
          aria-label={t("superadmin.audit.filter.enterprise")}
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
          <Text c="dimmed">{t("superadmin.audit.empty")}</Text>
        </Box>
      ) : (
        <Table.ScrollContainer minWidth={900}>
          <Table striped highlightOnHover withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t("superadmin.audit.table.at")}</Table.Th>
                <Table.Th>{t("superadmin.audit.table.action")}</Table.Th>
                <Table.Th>{t("superadmin.audit.table.entity_type")}</Table.Th>
                <Table.Th>{t("superadmin.audit.table.entity_id")}</Table.Th>
                <Table.Th>{t("superadmin.audit.table.enterprise")}</Table.Th>
                <Table.Th>{t("catalog.table.actions")}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.items.map((log) => (
                <Table.Tr key={log.id}>
                  <Table.Td>
                    <Text size="sm" c="dimmed" style={{ whiteSpace: "nowrap" }}>
                      {formatDate(log.at)}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Badge
                      color={actionColor(log.action)}
                      variant="light"
                      size="sm"
                    >
                      {log.action}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{log.entity_type}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs" c="dimmed" ff="monospace">
                      {log.entity_id ? log.entity_id.slice(0, 8) + "…" : "—"}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed">
                      {log.enterprise_id
                        ? (enterprisesData?.items.find(
                            (e) => e.id === log.enterprise_id,
                          )?.name ?? log.enterprise_id.slice(0, 8) + "…")
                        : "—"}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Tooltip label={t("superadmin.audit.view_json")}>
                      <ActionIcon
                        variant="subtle"
                        onClick={() => handleViewJson(log)}
                        aria-label={t("superadmin.audit.view_json")}
                        disabled={!log.before_json && !log.after_json}
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

      {/* JSON modal */}
      <JsonViewModal
        opened={jsonModalOpened}
        onClose={closeJsonModal}
        log={selectedLog}
      />
    </Stack>
  );
}
