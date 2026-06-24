/**
 * SuperadminEnterprisesPage — korxonalar boshqaruv sahifasi.
 *
 * Xususiyatlar:
 * - Qidiruv (name/INN) + status filter (active/suspended/hammasi)
 * - Jadval: checkbox, nom, INN, status, modullar soni, yaratilgan vaqt, amallar
 * - Bulk amallar: Suspend / Activate / O'chirish (tanlanganlar uchun)
 *   422 xatoni yutib, qolganlarini bajarishda davom etadi
 * - CSV export: joriy ro'yxatni client-side Blob sifatida yuklab olish
 * - Yaratish tugmasi → EnterpriseFormModal (yaratish)
 * - Tahrirlash → EnterpriseFormModal (tahrirlash)
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
  Checkbox,
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
  IconDownload,
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

// ─── CSV eksport ──────────────────────────────────────────────────────────────

function exportCsv(items: SuperadminEnterpriseOut[], t: (key: string) => string) {
  const header = [
    t("superadmin.table.name"),
    "INN",
    t("superadmin.table.status"),
    t("superadmin.table.modules_count"),
    t("superadmin.table.created_at"),
  ].join(",");

  const rows = items.map((ent) => {
    const escape = (v: string) => `"${v.replace(/"/g, '""')}"`;
    return [
      escape(ent.name),
      escape(ent.inn ?? ""),
      escape(ent.status),
      String(ent.enabled_modules.length),
      escape(formatDate(ent.created_at)),
    ].join(",");
  });

  const csv = [header, ...rows].join("\n");
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `enterprises_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// ─── Komponent ────────────────────────────────────────────────────────────────

export function SuperadminEnterprisesPage() {
  const { t } = useTranslation();
  const { showError } = useApiError();
  const navigate = useNavigate();

  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("");

  // Bulk select holati
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkDeleteOpened, { open: openBulkDelete, close: closeBulkDelete }] =
    useDisclosure(false);

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
  const items = data?.items ?? [];

  // Barcha/hech biri tanlangan holati
  const allSelected =
    items.length > 0 && items.every((e) => selectedIds.has(e.id));
  const someSelected = items.some((e) => selectedIds.has(e.id));

  const handleToggleAll = () => {
    if (allSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(items.map((e) => e.id)));
    }
  };

  const handleToggleRow = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Qidiruv o'zgarganda sahifani 1 ga qaytarish
  const handleSearchChange = useCallback((val: string) => {
    setSearch(val);
    setPage(1);
    setSelectedIds(new Set());
  }, []);

  const handleStatusChange = useCallback((val: string | null) => {
    setStatusFilter(val ?? "");
    setPage(1);
    setSelectedIds(new Set());
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

  // ─── Bulk amallar ──────────────────────────────────────────────────────────
  // Promise.allSettled — barcha so'rovlar parallel ketadi,
  // muvaffaqiyatsiz bo'lganlar (422 default korxona va boshqa xatolar)
  // notification'da ko'rsatiladi.

  const getEnterpriseName = (id: string): string =>
    items.find((e) => e.id === id)?.name ?? id;

  const handleBulkSuspend = async () => {
    const ids = Array.from(selectedIds);
    const results = await Promise.allSettled(
      ids.map((id) => suspendMutation.mutateAsync(id)),
    );
    setSelectedIds(new Set());

    const failedNames = results
      .map((r, i) => (r.status === "rejected" ? getEnterpriseName(ids[i]) : null))
      .filter(Boolean) as string[];
    const successCount = results.filter((r) => r.status === "fulfilled").length;

    if (successCount > 0) {
      notifications.show({
        color: "orange",
        message: t("superadmin.bulk.suspended_count", { count: successCount }),
      });
    }
    if (failedNames.length > 0) {
      notifications.show({
        color: "red",
        title: t("superadmin.bulk.failed_title"),
        message: t("superadmin.bulk.failed_names", {
          names: failedNames.join(", "),
        }),
        autoClose: 8000,
      });
    }
  };

  const handleBulkActivate = async () => {
    const ids = Array.from(selectedIds);
    const results = await Promise.allSettled(
      ids.map((id) => activateMutation.mutateAsync(id)),
    );
    setSelectedIds(new Set());

    const failedNames = results
      .map((r, i) => (r.status === "rejected" ? getEnterpriseName(ids[i]) : null))
      .filter(Boolean) as string[];
    const successCount = results.filter((r) => r.status === "fulfilled").length;

    if (successCount > 0) {
      notifications.show({
        color: "green",
        message: t("superadmin.bulk.activated_count", { count: successCount }),
      });
    }
    if (failedNames.length > 0) {
      notifications.show({
        color: "red",
        title: t("superadmin.bulk.failed_title"),
        message: t("superadmin.bulk.failed_names", {
          names: failedNames.join(", "),
        }),
        autoClose: 8000,
      });
    }
  };

  const handleBulkDelete = async () => {
    const ids = Array.from(selectedIds);
    const results = await Promise.allSettled(
      ids.map((id) => deleteMutation.mutateAsync(id)),
    );
    setSelectedIds(new Set());
    closeBulkDelete();

    const failedNames = results
      .map((r, i) => (r.status === "rejected" ? getEnterpriseName(ids[i]) : null))
      .filter(Boolean) as string[];
    const successCount = results.filter((r) => r.status === "fulfilled").length;

    if (successCount > 0) {
      notifications.show({
        color: "red",
        message: t("superadmin.bulk.deleted_count", { count: successCount }),
      });
    }
    if (failedNames.length > 0) {
      notifications.show({
        color: "orange",
        title: t("superadmin.bulk.failed_title"),
        message: t("superadmin.bulk.failed_names", {
          names: failedNames.join(", "),
        }),
        autoClose: 8000,
      });
    }
  };

  const handleCsvExport = () => {
    exportCsv(items, t);
  };

  const selectedCount = selectedIds.size;

  return (
    <Stack gap="md">
      {/* Sarlavha */}
      <Group justify="space-between">
        <Title order={3}>{t("nav.enterprises")}</Title>
        <Group gap="sm">
          {items.length > 0 && (
            <Button
              variant="default"
              leftSection={<IconDownload size={16} />}
              onClick={handleCsvExport}
              size="sm"
            >
              {t("superadmin.actions.export_csv")}
            </Button>
          )}
          <Button leftSection={<IconPlus size={16} />} onClick={handleCreateClick}>
            {t("superadmin.actions.create")}
          </Button>
        </Group>
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

      {/* Bulk panel — tanlanganlar mavjud bo'lganda */}
      {selectedCount > 0 && (
        <Group
          gap="sm"
          p="xs"
          bg="blue.0"
          style={{ borderRadius: 8, border: "1px solid var(--mantine-color-blue-2)" }}
        >
          <Text size="sm" fw={500}>
            {t("superadmin.bulk.selected_count", { count: selectedCount })}
          </Text>
          <Button
            size="xs"
            color="orange"
            variant="light"
            leftSection={<IconPlayerPause size={14} />}
            onClick={() => { void handleBulkSuspend(); }}
            loading={suspendMutation.isPending}
          >
            {t("superadmin.bulk.suspend")}
          </Button>
          <Button
            size="xs"
            color="green"
            variant="light"
            leftSection={<IconPlayerPlay size={14} />}
            onClick={() => { void handleBulkActivate(); }}
            loading={activateMutation.isPending}
          >
            {t("superadmin.bulk.activate")}
          </Button>
          <Button
            size="xs"
            color="red"
            variant="light"
            leftSection={<IconTrash size={14} />}
            onClick={openBulkDelete}
          >
            {t("superadmin.bulk.delete")}
          </Button>
          <Button
            size="xs"
            variant="subtle"
            color="gray"
            onClick={() => setSelectedIds(new Set())}
          >
            {t("superadmin.bulk.clear")}
          </Button>
        </Group>
      )}

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
      ) : !items.length ? (
        <Box py="xl" ta="center">
          <Text c="dimmed">{t("superadmin.table.empty")}</Text>
        </Box>
      ) : (
        <Table.ScrollContainer minWidth={840}>
          <Table striped highlightOnHover withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th w={40}>
                  <Checkbox
                    checked={allSelected}
                    indeterminate={someSelected && !allSelected}
                    onChange={handleToggleAll}
                    aria-label={t("superadmin.bulk.select_all")}
                  />
                </Table.Th>
                <Table.Th>{t("superadmin.table.name")}</Table.Th>
                <Table.Th>{t("superadmin.table.inn")}</Table.Th>
                <Table.Th>{t("superadmin.table.status")}</Table.Th>
                <Table.Th>{t("superadmin.table.modules_count")}</Table.Th>
                <Table.Th>{t("superadmin.table.created_at")}</Table.Th>
                <Table.Th>{t("catalog.table.actions")}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {items.map((ent) => (
                <Table.Tr
                  key={ent.id}
                  style={{ cursor: "pointer" }}
                  onClick={() => handleRowClick(ent)}
                >
                  <Table.Td onClick={(e) => e.stopPropagation()}>
                    <Checkbox
                      checked={selectedIds.has(ent.id)}
                      onChange={() => handleToggleRow(ent.id)}
                      aria-label={t("superadmin.bulk.select_row", {
                        name: ent.name,
                      })}
                    />
                  </Table.Td>
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

      {/* Bulk o'chirish tasdiqlash */}
      <ConfirmDeleteModal
        opened={bulkDeleteOpened}
        onClose={closeBulkDelete}
        onConfirm={() => { void handleBulkDelete(); }}
        title={t("superadmin.bulk.delete_title")}
        message={t("superadmin.bulk.delete_confirm", { count: selectedCount })}
        loading={deleteMutation.isPending}
      />
    </Stack>
  );
}
