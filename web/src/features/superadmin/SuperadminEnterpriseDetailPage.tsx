/**
 * SuperadminEnterpriseDetailPage — korxona tafsiloti sahifasi.
 *
 * Ko'rsatiladi:
 * - Korxona ma'lumoti: nom, INN, status, modullar, sanalar, foydalanuvchilar soni
 * - Adminlar ro'yxati — har birida "Parolni reset" tugmasi
 * - Parol reset modali → generatsiya qilingan parolni ko'rsatish + copy tugmasi
 * - Amallar: tahrirlash / suspend / activate / o'chirish
 *
 * Ma'lumot: GET /superadmin/enterprises/{id}
 */

import {
  ActionIcon,
  Alert,
  Badge,
  Box,
  Button,
  Code,
  CopyButton,
  Divider,
  Group,
  Loader,
  Modal,
  Paper,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import {
  IconArrowLeft,
  IconCheck,
  IconCopy,
  IconEdit,
  IconKey,
  IconPlayerPause,
  IconPlayerPlay,
  IconTrash,
} from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useNavigate, useParams } from "react-router-dom";
import {
  useEnterpriseDetail,
  useSuspendEnterprise,
  useActivateEnterprise,
  useDeleteEnterprise,
  useResetAdminPassword,
} from "./api/superadminApi";
import { EnterpriseFormModal } from "./components/EnterpriseFormModal";
import { ConfirmDeleteModal } from "@/components/ConfirmDeleteModal";
import { useApiError } from "@/hooks/useApiError";
import type { SuperadminEnterpriseDetailAdmin, SuperadminEnterpriseOut } from "./types";
import { formatDate } from "@/utils/date";

// ─── Status badge ─────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const { t } = useTranslation();
  return (
    <Badge color={status === "active" ? "green" : "orange"} variant="filled" size="md">
      {t(`superadmin.status.${status}`, { defaultValue: status })}
    </Badge>
  );
}

// ─── Parol reset modali ───────────────────────────────────────────────────────

interface ResetPasswordModalProps {
  opened: boolean;
  onClose: () => void;
  admin: SuperadminEnterpriseDetailAdmin | null;
  enterpriseId: string;
}

function ResetPasswordModal({
  opened,
  onClose,
  admin,
  enterpriseId,
}: ResetPasswordModalProps) {
  const { t } = useTranslation();
  const { showError } = useApiError();
  const resetMutation = useResetAdminPassword(enterpriseId);
  const [generatedPassword, setGeneratedPassword] = useState<string | null>(null);

  const handleReset = async () => {
    if (!admin) return;
    try {
      const result = await resetMutation.mutateAsync({
        user_id: admin.id,
        new_password: null, // backend o'zi generatsiya qiladi
      });
      setGeneratedPassword(result.new_password);
    } catch (err) {
      showError(err);
    }
  };

  const handleClose = () => {
    setGeneratedPassword(null);
    onClose();
  };

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={<Title order={4}>{t("superadmin.reset_password.title")}</Title>}
      size="sm"
      centered
      closeOnClickOutside={!resetMutation.isPending}
    >
      <Stack gap="md">
        {admin && (
          <Text size="sm">
            {t("superadmin.reset_password.confirm_for", { name: admin.full_name })}
          </Text>
        )}

        {generatedPassword ? (
          // Parol faqat bir marta ko'rsatiladi
          <Alert color="green" title={t("superadmin.reset_password.new_password_label")}>
            <Stack gap="xs">
              <Group gap="xs">
                <Code fz="lg" fw={700} style={{ letterSpacing: 2 }}>
                  {generatedPassword}
                </Code>
                <CopyButton value={generatedPassword} timeout={2000}>
                  {({ copied, copy }) => (
                    <Tooltip
                      label={copied ? t("superadmin.reset_password.copied") : t("superadmin.reset_password.copy")}
                      withArrow
                    >
                      <ActionIcon
                        color={copied ? "teal" : "gray"}
                        variant="subtle"
                        onClick={copy}
                        aria-label={copied ? t("superadmin.reset_password.copied") : t("superadmin.reset_password.copy")}
                      >
                        {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
                      </ActionIcon>
                    </Tooltip>
                  )}
                </CopyButton>
              </Group>
              <Text size="xs" c="dimmed">
                {t("superadmin.reset_password.one_time_warning")}
              </Text>
            </Stack>
          </Alert>
        ) : (
          <Button
            onClick={() => { void handleReset(); }}
            loading={resetMutation.isPending}
            leftSection={<IconKey size={16} />}
          >
            {t("superadmin.reset_password.generate")}
          </Button>
        )}

        <Group justify="flex-end">
          <Button variant="default" onClick={handleClose}>
            {t("common.close")}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

// ─── Asosiy komponent ─────────────────────────────────────────────────────────

export function SuperadminEnterpriseDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const { showError } = useApiError();
  const navigate = useNavigate();

  const [formOpened, { open: openForm, close: closeForm }] = useDisclosure(false);
  const [suspendOpened, { open: openSuspend, close: closeSuspend }] = useDisclosure(false);
  const [deleteOpened, { open: openDelete, close: closeDelete }] = useDisclosure(false);
  const [resetOpened, { open: openReset, close: closeReset }] = useDisclosure(false);
  const [selectedAdmin, setSelectedAdmin] =
    useState<SuperadminEnterpriseDetailAdmin | null>(null);

  const { data, isLoading, isError, error } = useEnterpriseDetail(id ?? "");
  const suspendMutation = useSuspendEnterprise();
  const activateMutation = useActivateEnterprise();
  const deleteMutation = useDeleteEnterprise();

  const handleResetClick = (admin: SuperadminEnterpriseDetailAdmin) => {
    setSelectedAdmin(admin);
    openReset();
  };

  const handleSuspend = async () => {
    if (!data) return;
    try {
      await suspendMutation.mutateAsync(data.id);
      notifications.show({
        color: "orange",
        message: t("superadmin.messages.enterprise_suspended", { name: data.name }),
      });
      closeSuspend();
    } catch (err) {
      showError(err);
    }
  };

  const handleActivate = async () => {
    if (!data) return;
    try {
      await activateMutation.mutateAsync(data.id);
      notifications.show({
        color: "green",
        message: t("superadmin.messages.enterprise_activated", { name: data.name }),
      });
    } catch (err) {
      showError(err);
    }
  };

  const handleDelete = async () => {
    if (!data) return;
    try {
      await deleteMutation.mutateAsync(data.id);
      notifications.show({
        color: "red",
        message: t("superadmin.messages.enterprise_deleted", { name: data.name }),
      });
      void navigate("/superadmin/enterprises");
    } catch (err) {
      showError(err);
    }
  };

  // Korxona ma'lumoti EnterpriseFormModal uchun SuperadminEnterpriseOut turiga moslashtirish
  const enterpriseForForm: SuperadminEnterpriseOut | null = data
    ? {
        id: data.id,
        name: data.name,
        inn: data.inn,
        status: data.status,
        enabled_modules: data.enabled_modules,
        version: data.version,
        created_at: data.created_at,
        updated_at: data.updated_at,
      }
    : null;

  return (
    <Stack gap="md">
      {/* Orqaga tugmasi */}
      <Group>
        <Button
          variant="subtle"
          leftSection={<IconArrowLeft size={16} />}
          onClick={() => void navigate("/superadmin/enterprises")}
        >
          {t("superadmin.detail.back")}
        </Button>
      </Group>

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
      ) : !data ? null : (
        <>
          {/* Sarlavha + amallar */}
          <Group justify="space-between" wrap="wrap">
            <Group gap="sm">
              <Title order={3}>{data.name}</Title>
              <StatusBadge status={data.status} />
            </Group>
            <Group gap="xs">
              <Button
                variant="default"
                leftSection={<IconEdit size={16} />}
                onClick={openForm}
              >
                {t("common.edit")}
              </Button>

              {data.status === "active" ? (
                <Button
                  color="orange"
                  variant="light"
                  leftSection={<IconPlayerPause size={16} />}
                  onClick={openSuspend}
                >
                  {t("superadmin.actions.suspend")}
                </Button>
              ) : (
                <Button
                  color="green"
                  variant="light"
                  leftSection={<IconPlayerPlay size={16} />}
                  onClick={() => { void handleActivate(); }}
                  loading={activateMutation.isPending}
                >
                  {t("superadmin.actions.activate")}
                </Button>
              )}

              <Button
                color="red"
                variant="light"
                leftSection={<IconTrash size={16} />}
                onClick={openDelete}
              >
                {t("common.delete")}
              </Button>
            </Group>
          </Group>

          {/* Korxona ma'lumoti */}
          <Paper withBorder p="md" radius="md">
            <Title order={5} mb="sm">{t("superadmin.detail.info_section")}</Title>
            <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} spacing="sm">
              <Box>
                <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
                  {t("superadmin.table.inn")}
                </Text>
                <Text size="sm" mt={2}>{data.inn ?? "—"}</Text>
              </Box>
              <Box>
                <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
                  {t("superadmin.detail.user_count")}
                </Text>
                <Text size="sm" mt={2}>{data.user_count}</Text>
              </Box>
              <Box>
                <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
                  {t("superadmin.table.modules_count")}
                </Text>
                <Text size="sm" mt={2}>{data.enabled_modules.length}</Text>
              </Box>
              <Box>
                <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
                  {t("superadmin.table.created_at")}
                </Text>
                <Text size="sm" mt={2}>{formatDate(data.created_at)}</Text>
              </Box>
              <Box>
                <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
                  {t("superadmin.detail.updated_at")}
                </Text>
                <Text size="sm" mt={2}>{formatDate(data.updated_at)}</Text>
              </Box>
            </SimpleGrid>

            {data.enabled_modules.length > 0 && (
              <>
                <Divider my="sm" />
                <Text size="xs" c="dimmed" tt="uppercase" fw={600} mb={6}>
                  {t("superadmin.form.modules")}
                </Text>
                <Group gap="xs">
                  {data.enabled_modules.map((mod) => (
                    <Badge key={mod} variant="outline" size="sm">
                      {t(`superadmin.modules.${mod}`, { defaultValue: mod })}
                    </Badge>
                  ))}
                </Group>
              </>
            )}
          </Paper>

          {/* Adminlar ro'yxati */}
          <Paper withBorder p="md" radius="md">
            <Title order={5} mb="sm">{t("superadmin.detail.admins_section")}</Title>
            {data.admins.length === 0 ? (
              <Text c="dimmed" size="sm">{t("superadmin.detail.no_admins")}</Text>
            ) : (
              <Table.ScrollContainer minWidth={600}>
                <Table striped withTableBorder>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>{t("users.table.full_name")}</Table.Th>
                      <Table.Th>{t("users.table.phone")}</Table.Th>
                      <Table.Th>{t("users.table.role")}</Table.Th>
                      <Table.Th>{t("users.table.status")}</Table.Th>
                      <Table.Th>{t("superadmin.table.created_at")}</Table.Th>
                      <Table.Th>{t("catalog.table.actions")}</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {data.admins.map((admin) => (
                      <Table.Tr key={admin.id}>
                        <Table.Td>
                          <Text size="sm" fw={500}>{admin.full_name}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm" c="dimmed">{admin.phone}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Badge variant="light" size="sm">
                            {t(`common.role.${admin.role}`, { defaultValue: admin.role })}
                          </Badge>
                        </Table.Td>
                        <Table.Td>
                          <Badge
                            color={admin.is_active ? "green" : "gray"}
                            variant="dot"
                            size="sm"
                          >
                            {admin.is_active
                              ? t("users.status.active")
                              : t("users.status.inactive")}
                          </Badge>
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm" c="dimmed">{formatDate(admin.created_at)}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Tooltip label={t("superadmin.reset_password.title")}>
                            <ActionIcon
                              variant="subtle"
                              color="violet"
                              onClick={() => handleResetClick(admin)}
                              aria-label={t("superadmin.reset_password.title")}
                            >
                              <IconKey size={16} />
                            </ActionIcon>
                          </Tooltip>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            )}
          </Paper>
        </>
      )}

      {/* Modallar */}
      {enterpriseForForm && (
        <EnterpriseFormModal
          opened={formOpened}
          onClose={closeForm}
          enterprise={enterpriseForForm}
        />
      )}

      <ConfirmDeleteModal
        opened={suspendOpened}
        onClose={closeSuspend}
        onConfirm={() => { void handleSuspend(); }}
        title={t("superadmin.suspend.title")}
        message={data ? t("superadmin.suspend.confirm", { name: data.name }) : ""}
        loading={suspendMutation.isPending}
      />

      <ConfirmDeleteModal
        opened={deleteOpened}
        onClose={closeDelete}
        onConfirm={() => { void handleDelete(); }}
        title={t("superadmin.delete.title")}
        message={data ? t("superadmin.delete.confirm", { name: data.name }) : ""}
        loading={deleteMutation.isPending}
      />

      <ResetPasswordModal
        opened={resetOpened}
        onClose={closeReset}
        admin={selectedAdmin}
        enterpriseId={id ?? ""}
      />
    </Stack>
  );
}
