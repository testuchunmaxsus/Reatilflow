/**
 * ContractsListPage — shartnomalar boshqaruv sahifasi.
 *
 * Xususiyatlar:
 * - Paginated jadval (Mantine Table) — server-side
 * - Filtrlar: status (active | expiring | expired)
 * - "Tugayotgan" (expiring) filtri — alohida tez-murojaat tugmasi
 * - RBAC: <Can permission="contracts:view"> — administrator, accountant ko'radi
 * - Yaratish / tahrirlash modal (ContractFormModal)
 * - Fayl yuklash modal (ContractFileUploadModal)
 * - O'chirish tasdiqlash (ConfirmDeleteModal — faqat administrator)
 * - Status DERIVED — faqat ko'rsatiladi (backend hisoblaydi)
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
import {
  IconEdit,
  IconPlus,
  IconTrash,
  IconFileUpload,
} from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { Can } from "@/rbac/Can";
import { useContracts, useDeleteContract } from "./api/contractsApi";
import { ContractFormModal } from "./components/ContractFormModal";
import { ContractFileUploadModal } from "./components/ContractFileUploadModal";
import { ConfirmDeleteModal } from "@/components/ConfirmDeleteModal";
import { useApiError } from "@/hooks/useApiError";
import type { ContractOut, ContractFilters } from "./types";

const PAGE_SIZE = 20;

// ─── Status badge rangi ───────────────────────────────────────────────────────

function statusBadgeColor(status: ContractOut["status"]): string {
  switch (status) {
    case "active":
      return "green";
    case "expiring":
      return "orange";
    case "expired":
      return "red";
    default:
      return "gray";
  }
}

// ─── Sana formatlash ──────────────────────────────────────────────────────────

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString("uz-UZ", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

// ─── Komponent ────────────────────────────────────────────────────────────────

export function ContractsListPage() {
  const { t } = useTranslation();
  const { showError } = useApiError();

  // Filtrlar
  const [statusFilter, setStatusFilter] = useState<
    "active" | "expiring" | "expired" | ""
  >("");
  const [page, setPage] = useState(1);
  const offset = (page - 1) * PAGE_SIZE;

  // Modal holatlari
  const [formOpened, { open: openForm, close: closeForm }] =
    useDisclosure(false);
  const [fileOpened, { open: openFile, close: closeFile }] =
    useDisclosure(false);
  const [deleteOpened, { open: openDelete, close: closeDelete }] =
    useDisclosure(false);

  const [editingContract, setEditingContract] = useState<
    ContractOut | undefined
  >(undefined);
  const [fileContract, setFileContract] = useState<ContractOut | null>(null);
  const [deletingContract, setDeletingContract] = useState<ContractOut | null>(
    null,
  );

  // Filtr params
  const filters: ContractFilters = {
    ...(statusFilter ? { status: statusFilter } : {}),
    limit: PAGE_SIZE,
    offset,
  };

  const { data, isLoading, isError, error } = useContracts(filters);
  const deleteContract = useDeleteContract();

  const handleCreateClick = () => {
    setEditingContract(undefined);
    openForm();
  };

  const handleEditClick = (contract: ContractOut) => {
    setEditingContract(contract);
    openForm();
  };

  const handleFileClick = (contract: ContractOut) => {
    setFileContract(contract);
    openFile();
  };

  const handleDeleteClick = (contract: ContractOut) => {
    setDeletingContract(contract);
    openDelete();
  };

  const handleConfirmDelete = async () => {
    if (!deletingContract) return;
    try {
      await deleteContract.mutateAsync(deletingContract.id);
      notifications.show({
        color: "orange",
        message: t("contracts.messages.deleted"),
      });
      closeDelete();
    } catch (err) {
      showError(err);
    }
  };

  // "Tugayotgan" tez-filtri
  const handleExpiringFilter = () => {
    setStatusFilter("expiring");
    setPage(1);
  };

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1;

  const statusFilterOptions = [
    { value: "", label: t("contracts.filter.all_statuses") },
    { value: "active", label: t("contracts.status.active") },
    { value: "expiring", label: t("contracts.status.expiring") },
    { value: "expired", label: t("contracts.status.expired") },
  ];

  return (
    <Can
      permission="contracts:view"
      fallback={
        <Box py="xl" ta="center">
          <Text c="dimmed">{t("contracts.access_denied")}</Text>
        </Box>
      }
    >
      <Stack gap="md">
        {/* Sarlavha va yaratish tugmasi */}
        <Group justify="space-between">
          <Title order={3}>{t("pages.contracts.title")}</Title>
          <Can permission="contracts:create">
            <Button
              leftSection={<IconPlus size={16} />}
              onClick={handleCreateClick}
            >
              {t("contracts.actions.create")}
            </Button>
          </Can>
        </Group>

        {/* Filtrlar */}
        <Group gap="sm" wrap="wrap">
          <Select
            data={statusFilterOptions}
            value={statusFilter}
            onChange={(v) => {
              setStatusFilter(
                (v ?? "") as "active" | "expiring" | "expired" | "",
              );
              setPage(1);
            }}
            w={200}
            aria-label={t("contracts.filter.status")}
            allowDeselect={false}
          />
          {/* Tugayotgan — tez-murojaat filtri */}
          <Button
            variant={statusFilter === "expiring" ? "filled" : "light"}
            color="orange"
            size="sm"
            onClick={handleExpiringFilter}
          >
            {t("contracts.filter.expiring_soon")}
          </Button>
          {statusFilter && (
            <Button
              variant="subtle"
              size="sm"
              onClick={() => {
                setStatusFilter("");
                setPage(1);
              }}
            >
              {t("contracts.filter.clear")}
            </Button>
          )}
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
            <Text c="dimmed">{t("contracts.table.empty")}</Text>
          </Box>
        ) : (
          <Table.ScrollContainer minWidth={900}>
            <Table striped highlightOnHover withTableBorder>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t("contracts.table.number")}</Table.Th>
                  <Table.Th>{t("contracts.table.store_id")}</Table.Th>
                  <Table.Th>{t("contracts.table.type")}</Table.Th>
                  <Table.Th>{t("contracts.table.valid_from")}</Table.Th>
                  <Table.Th>{t("contracts.table.valid_to")}</Table.Th>
                  <Table.Th>{t("contracts.table.status")}</Table.Th>
                  <Table.Th>{t("catalog.table.actions")}</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {data.items.map((contract) => (
                  <Table.Tr key={contract.id}>
                    <Table.Td>
                      <Text size="sm" fw={500}>
                        {contract.number}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" ff="monospace" c="dimmed" lineClamp={1}>
                        {contract.store_id}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">
                        {contract.contract_type
                          ? t(`contracts.type.${contract.contract_type}`)
                          : "—"}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">{formatDate(contract.valid_from)}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">{formatDate(contract.valid_to)}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Badge
                        color={statusBadgeColor(contract.status)}
                        variant="light"
                        size="sm"
                      >
                        {t(`contracts.status.${contract.status}`)}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Group gap={4}>
                        <Can permission="contracts:edit">
                          <Tooltip label={t("common.edit")}>
                            <ActionIcon
                              variant="subtle"
                              onClick={() => handleEditClick(contract)}
                              aria-label={t("common.edit")}
                            >
                              <IconEdit size={16} />
                            </ActionIcon>
                          </Tooltip>
                          <Tooltip label={t("contracts.actions.upload_file")}>
                            <ActionIcon
                              variant="subtle"
                              color="teal"
                              onClick={() => handleFileClick(contract)}
                              aria-label={t("contracts.actions.upload_file")}
                            >
                              <IconFileUpload size={16} />
                            </ActionIcon>
                          </Tooltip>
                        </Can>
                        <Can permission="contracts:delete">
                          <Tooltip label={t("common.delete")}>
                            <ActionIcon
                              variant="subtle"
                              color="red"
                              onClick={() => handleDeleteClick(contract)}
                              aria-label={t("common.delete")}
                            >
                              <IconTrash size={16} />
                            </ActionIcon>
                          </Tooltip>
                        </Can>
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
        <ContractFormModal
          opened={formOpened}
          onClose={closeForm}
          contract={editingContract}
        />
        <ContractFileUploadModal
          opened={fileOpened}
          onClose={closeFile}
          contract={fileContract}
        />
        <ConfirmDeleteModal
          opened={deleteOpened}
          onClose={closeDelete}
          onConfirm={() => { void handleConfirmDelete(); }}
          title={t("contracts.delete.title")}
          message={
            deletingContract
              ? t("contracts.delete.confirm", {
                  number: deletingContract.number,
                })
              : ""
          }
          loading={deleteContract.isPending}
        />
      </Stack>
    </Can>
  );
}
