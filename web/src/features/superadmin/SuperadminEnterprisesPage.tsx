/**
 * SuperadminEnterprisesPage — korxonalar boshqaruv sahifasi.
 *
 * Xususiyatlar:
 * - Jadval: nom, INN, status, modullar soni, yaratilgan vaqt, amallar
 * - Yaratish tugmasi → EnterpriseFormModal (yaratish)
 * - Tahrirlash → EnterpriseFormModal (tahrirlash, nom + modullar)
 * - Suspend / Activate tugmalari (tasdiqlash bilan)
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
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import {
  IconPlus,
  IconEdit,
  IconPlayerPause,
  IconPlayerPlay,
} from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import {
  useEnterprises,
  useSuspendEnterprise,
  useActivateEnterprise,
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

  const [page, setPage] = useState(1);
  const offset = (page - 1) * PAGE_SIZE;

  const [formOpened, { open: openForm, close: closeForm }] = useDisclosure(false);
  const [suspendOpened, { open: openSuspend, close: closeSuspend }] = useDisclosure(false);

  const [editingEnterprise, setEditingEnterprise] =
    useState<SuperadminEnterpriseOut | null>(null);
  const [suspendingEnterprise, setSuspendingEnterprise] =
    useState<SuperadminEnterpriseOut | null>(null);

  const { data, isLoading, isError, error } = useEnterprises(PAGE_SIZE, offset);
  const suspendMutation = useSuspendEnterprise();
  const activateMutation = useActivateEnterprise();

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1;

  const handleCreateClick = () => {
    setEditingEnterprise(null);
    openForm();
  };

  const handleEditClick = (ent: SuperadminEnterpriseOut) => {
    setEditingEnterprise(ent);
    openForm();
  };

  const handleSuspendClick = (ent: SuperadminEnterpriseOut) => {
    setSuspendingEnterprise(ent);
    openSuspend();
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

  const handleActivateClick = async (ent: SuperadminEnterpriseOut) => {
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

  return (
    <Stack gap="md">
      {/* Sarlavha */}
      <Group justify="space-between">
        <Title order={3}>{t("nav.enterprises")}</Title>
        <Button leftSection={<IconPlus size={16} />} onClick={handleCreateClick}>
          {t("superadmin.actions.create")}
        </Button>
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
                <Table.Tr key={ent.id}>
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
                    <Group gap={4}>
                      <Tooltip label={t("common.edit")}>
                        <ActionIcon
                          variant="subtle"
                          onClick={() => handleEditClick(ent)}
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
                            onClick={() => handleSuspendClick(ent)}
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
                            onClick={() => { void handleActivateClick(ent); }}
                            aria-label={t("superadmin.actions.activate")}
                          >
                            <IconPlayerPlay size={16} />
                          </ActionIcon>
                        </Tooltip>
                      )}
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
    </Stack>
  );
}
