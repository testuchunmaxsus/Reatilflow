/**
 * CustomerListPage — do'konlar ro'yxati sahifasi.
 *
 * Xususiyatlar:
 * - Paginated jadval (Mantine Table)
 * - Qidiruv: nom/INN/telefon (blind-index backend)
 * - RBAC: yaratish/tahrirlash/o'chirish/agent_biriktirish tugmalari <Can>
 * - PII ko'rsatish: backend qaytargan bo'lsa ko'rsatiladi (kuryer uchun yashirilgan)
 * - StoreLimitedOut moslashish: inn/phone yo'q bo'lsa "—" ko'rsatiladi
 * - i18n uz/ru
 * - Loading / empty / error holatlari
 */

import {
  ActionIcon,
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
  IconEdit,
  IconPlus,
  IconSearch,
  IconTrash,
  IconUserCheck,
} from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { Can } from "@/rbac/Can";
import { useDeleteStore, useStores } from "./api/customersApi";
import { StoreFormModal } from "./components/StoreFormModal";
import { AssignAgentModal } from "./components/AssignAgentModal";
import { ConfirmDeleteModal } from "@/components/ConfirmDeleteModal";
import { useApiError } from "@/hooks/useApiError";
import { useDebounce } from "@/hooks/useDebounce";
import type { StoreOut } from "@/api/types";

const PAGE_SIZE = 20;

// ─── Qidiruv rejimi ───────────────────────────────────────────────────────────

type SearchMode = "name" | "inn" | "phone";

// ─── Komponent ────────────────────────────────────────────────────────────────

export function CustomerListPage() {
  const { t } = useTranslation();
  const { showError } = useApiError();

  // Qidiruv
  const [searchInput, setSearchInput] = useState("");
  const [searchMode, setSearchMode] = useState<SearchMode>("name");
  const debouncedSearch = useDebounce(searchInput, 300);

  // Sahifalash
  const [page, setPage] = useState(1);
  const offset = (page - 1) * PAGE_SIZE;

  // Modal holatlari
  const [formOpened, { open: openForm, close: closeForm }] = useDisclosure(false);
  const [assignOpened, { open: openAssign, close: closeAssign }] = useDisclosure(false);
  const [deleteOpened, { open: openDelete, close: closeDelete }] = useDisclosure(false);
  const [editingStore, setEditingStore] = useState<StoreOut | undefined>(undefined);
  const [selectedStore, setSelectedStore] = useState<StoreOut | null>(null);
  const [deletingStore, setDeletingStore] = useState<StoreOut | null>(null);

  // Filtr params
  const filters = {
    search_name: searchMode === "name" ? debouncedSearch || undefined : undefined,
    search_inn: searchMode === "inn" ? debouncedSearch || undefined : undefined,
    search_phone: searchMode === "phone" ? debouncedSearch || undefined : undefined,
    limit: PAGE_SIZE,
    offset,
  };

  const { data, isLoading, isError, error } = useStores(filters);
  const deleteStore = useDeleteStore();

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchInput(e.target.value);
    setPage(1);
  };

  const handleCreateClick = () => {
    setEditingStore(undefined);
    openForm();
  };

  const handleEditClick = (store: StoreOut) => {
    setEditingStore(store);
    openForm();
  };

  const handleAssignClick = (store: StoreOut) => {
    setSelectedStore(store);
    openAssign();
  };

  const handleDeleteClick = (store: StoreOut) => {
    setDeletingStore(store);
    openDelete();
  };

  const handleConfirmDelete = async () => {
    if (!deletingStore) return;
    try {
      await deleteStore.mutateAsync(deletingStore.id);
      notifications.show({
        color: "green",
        message: t("customers.messages.store_deleted"),
      });
      closeDelete();
    } catch (err) {
      showError(err);
    }
  };

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1;

  const searchModeOptions = [
    { value: "name", label: t("customers.filter.search_by_name") },
    { value: "inn", label: t("customers.filter.search_by_inn") },
    { value: "phone", label: t("customers.filter.search_by_phone") },
  ];

  // PII yashiringan bo'lsa "—" ko'rsatamiz (kuryer roli: StoreLimitedOut)
  const piiValue = (value: string | null | undefined) =>
    value !== null && value !== undefined ? value : "—";

  return (
    <Stack gap="md">
      {/* Sarlavha va yaratish tugmasi */}
      <Group justify="space-between">
        <Title order={3}>{t("pages.customers.title")}</Title>
        <Can permission="customers:create">
          <Button leftSection={<IconPlus size={16} />} onClick={handleCreateClick}>
            {t("customers.actions.create")}
          </Button>
        </Can>
      </Group>

      {/* Qidiruv */}
      <Group gap="sm" wrap="wrap">
        <Select
          data={searchModeOptions}
          value={searchMode}
          onChange={(v) => {
            setSearchMode((v as SearchMode) ?? "name");
            setSearchInput("");
            setPage(1);
          }}
          w={180}
        />
        <TextInput
          placeholder={t("customers.filter.search_placeholder")}
          leftSection={<IconSearch size={16} />}
          value={searchInput}
          onChange={handleSearchChange}
          w={280}
          aria-label={t("customers.filter.search_placeholder")}
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
          <Text c="dimmed">{t("customers.table.empty")}</Text>
        </Box>
      ) : (
        <Table.ScrollContainer minWidth={800}>
          <Table striped highlightOnHover withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t("customers.table.name")}</Table.Th>
                <Table.Th>{t("customers.table.phone")}</Table.Th>
                <Table.Th>{t("customers.table.inn")}</Table.Th>
                <Table.Th>{t("customers.table.owner_name")}</Table.Th>
                <Table.Th>{t("customers.table.address")}</Table.Th>
                <Table.Th>{t("customers.table.credit_limit")}</Table.Th>
                <Table.Th>{t("catalog.table.actions")}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.items.map((store) => (
                <Table.Tr key={store.id}>
                  <Table.Td>
                    <Text size="sm" fw={500} lineClamp={1}>
                      {store.name}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" ff="monospace">
                      {piiValue(store.phone)}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" ff="monospace" c="dimmed">
                      {piiValue(store.inn)}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{piiValue(store.owner_name)}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" lineClamp={1}>
                      {store.address ?? "—"}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">
                      {store.credit_limit != null
                        ? new Intl.NumberFormat("uz-UZ").format(
                            Number(store.credit_limit),
                          )
                        : "—"}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Group gap={4}>
                      <Can permission="customers:edit">
                        <Tooltip label={t("common.edit")}>
                          <ActionIcon
                            variant="subtle"
                            onClick={() => handleEditClick(store)}
                            aria-label={t("common.edit")}
                          >
                            <IconEdit size={16} />
                          </ActionIcon>
                        </Tooltip>
                        <Tooltip label={t("customers.actions.assign_agent")}>
                          <ActionIcon
                            variant="subtle"
                            color="teal"
                            onClick={() => handleAssignClick(store)}
                            aria-label={t("customers.actions.assign_agent")}
                          >
                            <IconUserCheck size={16} />
                          </ActionIcon>
                        </Tooltip>
                      </Can>
                      <Can permission="customers:delete">
                        <Tooltip label={t("common.delete")}>
                          <ActionIcon
                            variant="subtle"
                            color="red"
                            onClick={() => handleDeleteClick(store)}
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
      <StoreFormModal
        opened={formOpened}
        onClose={closeForm}
        store={editingStore}
      />
      <AssignAgentModal
        opened={assignOpened}
        onClose={closeAssign}
        store={selectedStore}
      />
      <ConfirmDeleteModal
        opened={deleteOpened}
        onClose={closeDelete}
        onConfirm={() => { void handleConfirmDelete(); }}
        title={t("customers.delete.title")}
        message={
          deletingStore
            ? t("customers.delete.confirm", { name: deletingStore.name })
            : ""
        }
        loading={deleteStore.isPending}
      />
    </Stack>
  );
}
