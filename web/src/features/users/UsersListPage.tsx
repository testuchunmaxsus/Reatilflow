/**
 * UsersListPage — foydalanuvchilar boshqaruv sahifasi.
 *
 * Xususiyatlar:
 * - Paginated jadval (Mantine Table) — server-side
 * - Filtrlar: rol, holat (aktiv/nofaol)
 * - RBAC: <Can permission="rbac:view"> — faqat administrator
 * - Yaratish / tahrirlash modal (UserFormModal)
 * - Deaktivatsiya tasdiqlash (ConfirmDeleteModal — "deactivate" sifatida)
 * - Aktivlashtirish: PATCH /users/{id}/activate (deactivate teskarisi)
 * - Agent → do'kon biriktirish (AssignStoreModal — mavjud do'konlardan tanlash)
 * - PII: telefon backend qaytargan qiymat (admin uchun to'liq, maskalanmagan)
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
  IconUserOff,
  IconUserCheck,
  IconBuildingStore,
} from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { Can } from "@/rbac/Can";
import { useUsers, useDeactivateUser, useActivateUser } from "./api/usersApi";
import { UserFormModal } from "./components/UserFormModal";
import { AssignStoreModal } from "./components/AssignStoreModal";
import { ConfirmDeleteModal } from "@/components/ConfirmDeleteModal";
import { useApiError } from "@/hooks/useApiError";
import type { UserOut, UserRole, UserFilters } from "./types";

const PAGE_SIZE = 20;

// ─── Rol badge rangi ──────────────────────────────────────────────────────────

function roleBadgeColor(role: UserRole): string {
  switch (role) {
    case "administrator":
      return "red";
    case "agent":
      return "blue";
    case "courier":
      return "teal";
    case "accountant":
      return "violet";
    case "store":
      return "orange";
    default:
      return "gray";
  }
}

// ─── Telefon maskalash (qisman) ───────────────────────────────────────────────

function maskPhone(phone: string): string {
  // PII: oxirgi 4 raqamdan boshqasini yashiramiz (admin ko'radi lekin cautious UI)
  // Backend to'liq qaytaradi — faqat UI da qisman ko'rsatamiz
  if (phone.length <= 4) return phone;
  return phone.slice(0, -4).replace(/\d/g, "*") + phone.slice(-4);
}

// ─── Komponent ────────────────────────────────────────────────────────────────

export function UsersListPage() {
  const { t } = useTranslation();
  const { showError } = useApiError();

  // Filtrlar
  const [roleFilter, setRoleFilter] = useState<UserRole | "">("");
  const [statusFilter, setStatusFilter] = useState<"" | "true" | "false">("");
  const [page, setPage] = useState(1);
  const offset = (page - 1) * PAGE_SIZE;

  // Modal holatlari
  const [formOpened, { open: openForm, close: closeForm }] =
    useDisclosure(false);
  const [assignOpened, { open: openAssign, close: closeAssign }] =
    useDisclosure(false);
  const [deactivateOpened, { open: openDeactivate, close: closeDeactivate }] =
    useDisclosure(false);

  const [editingUser, setEditingUser] = useState<UserOut | undefined>(
    undefined,
  );
  const [selectedUser, setSelectedUser] = useState<UserOut | null>(null);
  const [deactivatingUser, setDeactivatingUser] = useState<UserOut | null>(
    null,
  );

  // Filtr params
  const filters: UserFilters = {
    ...(roleFilter ? { role: roleFilter } : {}),
    ...(statusFilter !== "" ? { is_active: statusFilter === "true" } : {}),
    limit: PAGE_SIZE,
    offset,
  };

  const { data, isLoading, isError, error } = useUsers(filters);
  const deactivateUser = useDeactivateUser();
  const activateUser = useActivateUser();

  const handleCreateClick = () => {
    setEditingUser(undefined);
    openForm();
  };

  const handleEditClick = (user: UserOut) => {
    setEditingUser(user);
    openForm();
  };

  const handleAssignClick = (user: UserOut) => {
    setSelectedUser(user);
    openAssign();
  };

  const handleDeactivateClick = (user: UserOut) => {
    setDeactivatingUser(user);
    openDeactivate();
  };

  const handleConfirmDeactivate = async () => {
    if (!deactivatingUser) return;
    try {
      await deactivateUser.mutateAsync(deactivatingUser.id);
      notifications.show({
        color: "orange",
        message: t("users.messages.user_deactivated"),
      });
      closeDeactivate();
    } catch (err) {
      showError(err);
    }
  };

  // Aktivlashtirish — backend PATCH /users/{id}/activate (deactivate teskarisi).
  const handleActivateClick = async (user: UserOut) => {
    try {
      await activateUser.mutateAsync(user.id);
      notifications.show({
        color: "green",
        message: t("users.messages.user_activated"),
      });
    } catch (err) {
      showError(err);
    }
  };

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1;

  const roleFilterOptions = [
    { value: "", label: t("users.filter.all_roles") },
    { value: "administrator", label: t("common.role.administrator") },
    { value: "agent", label: t("common.role.agent") },
    { value: "courier", label: t("common.role.courier") },
    { value: "accountant", label: t("common.role.accountant") },
    { value: "store", label: t("common.role.store") },
  ];

  const statusFilterOptions = [
    { value: "", label: t("users.filter.all_statuses") },
    { value: "true", label: t("users.filter.active") },
    { value: "false", label: t("users.filter.inactive") },
  ];

  return (
    <Can permission="rbac:view" fallback={
      <Box py="xl" ta="center">
        <Text c="dimmed">{t("users.access_denied")}</Text>
      </Box>
    }>
      <Stack gap="md">
        {/* Sarlavha va yaratish tugmasi */}
        <Group justify="space-between">
          <Title order={3}>{t("pages.users.title")}</Title>
          <Can permission="rbac:create">
            <Button
              leftSection={<IconPlus size={16} />}
              onClick={handleCreateClick}
            >
              {t("users.actions.create")}
            </Button>
          </Can>
        </Group>

        {/* Filtrlar */}
        <Group gap="sm" wrap="wrap">
          <Select
            data={roleFilterOptions}
            value={roleFilter}
            onChange={(v) => {
              setRoleFilter((v ?? "") as UserRole | "");
              setPage(1);
            }}
            w={180}
            aria-label={t("users.filter.role")}
            allowDeselect={false}
          />
          <Select
            data={statusFilterOptions}
            value={statusFilter}
            onChange={(v) => {
              setStatusFilter((v ?? "") as "" | "true" | "false");
              setPage(1);
            }}
            w={160}
            aria-label={t("users.filter.status")}
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
            <Text c="dimmed">{t("users.table.empty")}</Text>
          </Box>
        ) : (
          <Table.ScrollContainer minWidth={900}>
            <Table striped highlightOnHover withTableBorder>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t("users.table.full_name")}</Table.Th>
                  <Table.Th>{t("users.table.phone")}</Table.Th>
                  <Table.Th>{t("users.table.role")}</Table.Th>
                  <Table.Th>{t("users.table.status")}</Table.Th>
                  <Table.Th>{t("users.table.branch")}</Table.Th>
                  <Table.Th>{t("catalog.table.actions")}</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {data.items.map((user) => (
                  <Table.Tr key={user.id}>
                    <Table.Td>
                      <Text size="sm" fw={500} lineClamp={1}>
                        {user.full_name}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" ff="monospace">
                        {maskPhone(user.phone)}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Badge color={roleBadgeColor(user.role)} variant="light" size="sm">
                        {t(`common.role.${user.role}`)}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Badge
                        color={user.is_active ? "green" : "gray"}
                        variant="dot"
                        size="sm"
                      >
                        {user.is_active
                          ? t("users.status.active")
                          : t("users.status.inactive")}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" c="dimmed">
                        {user.branch_id ?? "—"}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Group gap={4}>
                        <Can permission="rbac:edit">
                          <Tooltip label={t("common.edit")}>
                            <ActionIcon
                              variant="subtle"
                              onClick={() => handleEditClick(user)}
                              aria-label={t("common.edit")}
                            >
                              <IconEdit size={16} />
                            </ActionIcon>
                          </Tooltip>

                          {/* Agent uchun do'kon biriktirish */}
                          {user.role === "agent" && (
                            <Tooltip label={t("users.actions.assign_store")}>
                              <ActionIcon
                                variant="subtle"
                                color="teal"
                                onClick={() => handleAssignClick(user)}
                                aria-label={t("users.actions.assign_store")}
                              >
                                <IconBuildingStore size={16} />
                              </ActionIcon>
                            </Tooltip>
                          )}

                          {/* Deaktivatsiya / aktivlashtirish */}
                          {user.is_active ? (
                            <Tooltip label={t("users.actions.deactivate")}>
                              <ActionIcon
                                variant="subtle"
                                color="orange"
                                onClick={() => handleDeactivateClick(user)}
                                aria-label={t("users.actions.deactivate")}
                              >
                                <IconUserOff size={16} />
                              </ActionIcon>
                            </Tooltip>
                          ) : (
                            <Tooltip label={t("users.actions.activate")}>
                              <ActionIcon
                                variant="subtle"
                                color="green"
                                onClick={() => { void handleActivateClick(user); }}
                                aria-label={t("users.actions.activate")}
                              >
                                <IconUserCheck size={16} />
                              </ActionIcon>
                            </Tooltip>
                          )}
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
        <UserFormModal
          opened={formOpened}
          onClose={closeForm}
          user={editingUser}
        />
        <AssignStoreModal
          opened={assignOpened}
          onClose={closeAssign}
          user={selectedUser}
        />
        <ConfirmDeleteModal
          opened={deactivateOpened}
          onClose={closeDeactivate}
          onConfirm={() => { void handleConfirmDeactivate(); }}
          title={t("users.deactivate.title")}
          message={
            deactivatingUser
              ? t("users.deactivate.confirm", {
                  name: deactivatingUser.full_name,
                })
              : ""
          }
          loading={deactivateUser.isPending}
        />
      </Stack>
    </Can>
  );
}
