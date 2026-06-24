/**
 * SuperadminEnterprisesPage — korxonalar boshqaruv sahifasi.
 *
 * Xususiyatlar:
 * - Qidiruv (name/INN) + status filter (active/suspended/hammasi)
 * - Jadval: nom, INN, status, modullar soni, yaratilgan vaqt, amallar
 * - Yaratish tugmasi → EnterpriseFormModal (yaratish)
 * - Tahrirlash → EnterpriseFormModal (tahrirlash, nom + modullar)
 * - Suspend / Activate tugmalari (tasdiqlash bilan)
 * - O'chirish tugmasi + ConfirmDeleteModal (DELETE)
 * - Qator bosilsa → /superadmin/enterprises/:id tafsilot sahifasi
 * - Paginated (20 ta/sahifa)
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
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import {
  IconPlus,
  IconEdit,
  IconPlayerPause,
  IconPlayerPlay,
  IconTrash,
  IconSearch,
} from "@tabler/icons-react";
import { useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useNavigate } from "react-router-dom";
import {
  useEnterprises,
  useSuspendEnterprise,
  useActivateEnterprise,
  useDeleteEnterprise,
} from "./api/superadminApi";
import { EnterpriseFormModal } from "./components/EnterpriseFormModal";
import { ConfirmDeleteModal } from "@/components/ConfirmDeleteModal";
import { useApiError } from "@/hooks/useApiError";
import type { SuperadminEnterpriseOut } from "./types";
import { formatDate } from "@/utils/date";

const PAGE_SIZE = 20;

// ─── Status badge ─────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const { t } = useTranslation();
  return (
    <Badge
      color={status === "active" ? "green" : "orange"}
      variant="dot"
      size="sm"
    >
      {t(`superadmin.status.${status}`, { defaultValue: status })}
    </Badge>
  );
}

// ─── Komponent ────────────────────────────────────────────────────────────────

export function SuperadminEnterprisesPage() {
  const { t } = useTranslation();
  const { showError } = useApiError();
  const navigate = useNavigate();

  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("");

  const offset = (page - 1) * PAGE_SIZE;

  const [formOpened, { open: openForm, close: closeForm }] = useDisclosure(false);
  const [suspendOpened, { open: openSuspend, close: closeSuspend }] = useDisclosure(false);
  const [deleteOpened, { open: openDelete, close: closeDelete }] = useDisclosure(false);

  const [editingEnterprise, setEditingEnterprise] =
    useState<SuperadminEnterpriseOut | null>(null);
  const [suspendingEnterprise, setSuspendingEnterprise] =
    useState<SuperadminEnterpriseOut | null>(null);
  const [deletingEnterprise, setDeletingEnterprise] =
    useState<SuperadminEnterpriseOut | null>(null);

  const { data, isLoading, isError, error } = useEnterprises({
    search,
    status: statusFilter,
    limit: PAGE_SIZE,
    offset,
  });
  const suspendMutation = useSuspendEnterprise();
  const activateMutation = useActivateEnterprise();
  const deleteMutation = useDeleteEnterprise();

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1;

  // Qidiruv o'zgarganda sahifani 1 ga qaytarish
  const handleSearchChange = useCallback((val: string) => {
    setSearch(val);
    setPage(1);
  }, []);

  const handleStatusChange = useCallback((val: string | null) => {
    setStatusFilter(val ?? "");
    setPage(1);
  }, []);

  const handleCreateClick = () => {
    setEditingEnterprise(null);
    openForm();
  };

  const handleEditClick = (e: React.MouseEvent, ent: SuperadminEnterpriseOut) => {
    e.stopPropagation();
    setEditingEnterprise(ent);
    openForm();
  };

  const handleSuspendClick = (e: React.MouseEvent, ent: SuperadminEnterpriseOut) => {
    e.stopPropagation();
    setSuspendingEnterprise(ent);
    openSuspend();
  };

  const handleDeleteClick = (e: React.MouseEvent, ent: SuperadminEnterpriseOut) => {
    e.stopPropagation();
    setDeletingEnterprise(ent);
    openDelete();
  };

  const handleConfirmSuspend = async () => {
    if (!suspendingEnterprise) return;
    try {
      await suspendMutation.mutateAsync(suspendingEnterprise.id);
      notifications.show({
        color: "orange",
        message: t("superadmin.messages.enterprise_suspended", {
          name: suspendingEnterprise.name,
        }),
      });
      closeSuspend();
    } catch (err) {
      showError(err);
    }
  };

  const handleActivateClick = async (e: React.MouseEvent, ent: SuperadminEnterpriseOut) => {
    e.stopPropagation();
    try {
      await activateMutation.mutateAsync(ent.id);
      notifications.show({
        color: "green",
        message: t("superadmin.messages.enterprise_activated", {
          name: ent.name,
        }),
      });
    } catch (err) {
      showError(err);
    }
  };

  const handleConfirmDelete = async () => {
    if (!deletingEnterprise) return;
    try {
      await deleteMutation.mutateAsync(deletingEnterprise.id);
      notifications.show({
        color: "red",
        message: t("superadmin.messages.enterprise_deleted", {
          name: deletingEnterprise.name,
        }),
      });
      closeDelete();
    } catch (err) {
      showError(err);
    }
  };

  const handleRowClick = (ent: SuperadminEnterpriseOut) => {
    void navigate(`/superadmin/enterprises/${ent.id}`);
  };

  return (
    <Stack gap="md">
      {/* Sarlavha */}
      <Group justify="space-between">
        <Title order={3}>{t("nav.enterprises")}</Title>
        <Button leftSection={<IconPlus size={16} />} onClick={handleCreateClick}>
          {t("superadmin.actions.create")}
        </Button>
      </Group>

      {/* Filtrlar */}
      <Group gap="sm">
        <TextInput
          placeholder={t("superadmin.filter.search_placeholder")}
          leftSection={<IconSearch size={16} />}
          value={search}
          onChange={(e) => handleSearchChange(e.currentTarget.value)}
          w={260}
          aria-label={t("superadmin.filter.search_placeholder")}
        />
        <Select
          placeholder={t("superadmin.filter.all_statuses")}
          value={statusFilter || null}
          onChange={handleStatusChange}
          data={[
            { value: "active", label: t("superadmin.status.active") },
            { value: "suspended", label: t("superadmin.status.suspended") },
          ]}
          clearable
          w={180}
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
          <Text c="dimmed">{t("superadmin.table.empty")}</Text>
        </Box>
      ) : (
        <Table.ScrollContainer minWidth={800}>
          <Table striped highlightOnHover withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t("superadmin.table.name")}</Table.Th>
                <Table.Th>{t("superadmin.table.inn")}</Table.Th>
                <Table.Th>{t("superadmin.table.status")}</Table.Th>
                <Table.Th>{t("superadmin.table.modules_count")}</Table.Th>
                <Table.Th>{t("superadmin.table.created_at")}</Table.Th>
                <Table.Th>{t("catalog.table.actions")}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.items.map((ent) => (
                <Table.Tr
                  key={ent.id}
                  style={{ cursor: "pointer" }}
                  onClick={() => handleRowClick(ent)}
                >
                  <Table.Td>
                    <Text size="sm" fw={500}>
                      {ent.name}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed">
                      {ent.inn ?? "—"}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <StatusBadge status={ent.status} />
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{ent.enabled_modules.length}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed">
                      {formatDate(ent.created_at)}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Group gap={4} onClick={(e) => e.stopPropagation()}>
                      <Tooltip label={t("common.edit")}>
                        <ActionIcon
                          variant="subtle"
                          onClick={(e) => handleEditClick(e, ent)}
                          aria-label={t("common.edit")}
                        >
                          <IconEdit size={16} />
                        </ActionIcon>
                      </Tooltip>

                      {ent.status === "active" ? (
                        <Tooltip label={t("superadmin.actions.suspend")}>
                          <ActionIcon
                            variant="subtle"
                            color="orange"
                            onClick={(e) => handleSuspendClick(e, ent)}
                            aria-label={t("superadmin.actions.suspend")}
                          >
                            <IconPlayerPause size={16} />
                          </ActionIcon>
                        </Tooltip>
                      ) : (
                        <Tooltip label={t("superadmin.actions.activate")}>
                          <ActionIcon
                            variant="subtle"
                            color="green"
                            onClick={(e) => { void handleActivateClick(e, ent); }}
                            aria-label={t("superadmin.actions.activate")}
                          >
                            <IconPlayerPlay size={16} />
                          </ActionIcon>
                        </Tooltip>
                      )}

                      <Tooltip label={t("common.delete")}>
                        <ActionIcon
                          variant="subtle"
                          color="red"
                          onClick={(e) => handleDeleteClick(e, ent)}
                          aria-label={t("common.delete")}
                        >
                          <IconTrash size={16} />
                        </ActionIcon>
                      </Tooltip>
                    </Group>
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
      <EnterpriseFormModal
        opened={formOpened}
        onClose={closeForm}
        enterprise={editingEnterprise}
      />

      <ConfirmDeleteModal
        opened={suspendOpened}
        onClose={closeSuspend}
        onConfirm={() => { void handleConfirmSuspend(); }}
        title={t("superadmin.suspend.title")}
        message={
          suspendingEnterprise
            ? t("superadmin.suspend.confirm", { name: suspendingEnterprise.name })
            : ""
        }
        loading={suspendMutation.isPending}
      />

      <ConfirmDeleteModal
        opened={deleteOpened}
        onClose={closeDelete}
        onConfirm={() => { void handleConfirmDelete(); }}
        title={t("superadmin.delete.title")}
        message={
          deletingEnterprise
            ? t("superadmin.delete.confirm", { name: deletingEnterprise.name })
            : ""
        }
        loading={deleteMutation.isPending}
      />
    </Stack>
  );
}
