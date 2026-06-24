/**
 * EnterpriseFormModal — korxona yaratish va tahrirlash modali.
 *
 * Yaratish:
 *   - nom, INN (ixtiyoriy), enabled_modules (checkbox)
 *   - Birinchi admin: ism, telefon, parol, til
 *
 * Tahrirlash:
 *   - nom, enabled_modules
 *   - Birinchi admin yo'q (mavjud admin o'zgartirilmaydi)
 */

import {
  ActionIcon,
  Box,
  Button,
  Checkbox,
  CopyButton,
  Group,
  Modal,
  PasswordInput,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import { IconRefresh, IconCheck, IconCopy } from "@tabler/icons-react";
import { useForm } from "@mantine/form";
import { useTranslation } from "react-i18next";
import { notifications } from "@mantine/notifications";
import { useCreateEnterprise, useUpdateEnterprise } from "../api/superadminApi";
import { useApiError } from "@/hooks/useApiError";
import type { SuperadminEnterpriseOut } from "../types";
import { ALL_MODULE_KEYS_FRONTEND } from "../constants";

// ─── Kuchli tasodifiy parol generatsiya (14 belgi) ───────────────────────────

const PASSWORD_CHARS =
  "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";

function generateStrongPassword(length = 14): string {
  const array = new Uint8Array(length);
  crypto.getRandomValues(array);
  return Array.from(array)
    .map((b) => PASSWORD_CHARS[b % PASSWORD_CHARS.length])
    .join("");
}

interface EnterpriseFormModalProps {
  opened: boolean;
  onClose: () => void;
  /** Tahrirlash uchun — null = yangi korxona */
  enterprise?: SuperadminEnterpriseOut | null;
}

interface CreateFormValues {
  name: string;
  inn: string;
  enabled_modules: string[];
  admin_full_name: string;
  admin_phone: string;
  admin_password: string;
  admin_locale: "uz" | "ru";
}

interface EditFormValues {
  name: string;
  enabled_modules: string[];
}

export function EnterpriseFormModal({
  opened,
  onClose,
  enterprise,
}: EnterpriseFormModalProps) {
  const { t } = useTranslation();
  const { showError } = useApiError();
  const isEdit = !!enterprise;

  const createEnterprise = useCreateEnterprise();
  const updateEnterprise = useUpdateEnterprise();

  // ─── Yaratish formasi ────────────────────────────────────────────────────────

  const createForm = useForm<CreateFormValues>({
    initialValues: {
      name: "",
      inn: "",
      enabled_modules: [...ALL_MODULE_KEYS_FRONTEND],
      admin_full_name: "",
      admin_phone: "",
      admin_password: "",
      admin_locale: "uz",
    },
    validate: {
      name: (v) => (v.trim() ? null : t("superadmin.form.name_required")),
      admin_full_name: (v) =>
        v.trim() ? null : t("superadmin.form.admin_name_required"),
      admin_phone: (v) => {
        if (!v.trim()) return t("validation.phone_required");
        if (!/^\+998\d{9}$/.test(v.trim())) return t("validation.phone_format");
        return null;
      },
      admin_password: (v) =>
        v.length >= 6 ? null : t("users.form.password_min"),
    },
  });

  // ─── Tahrirlash formasi ──────────────────────────────────────────────────────

  const editForm = useForm<EditFormValues>({
    initialValues: {
      name: enterprise?.name ?? "",
      enabled_modules: enterprise?.enabled_modules ?? [...ALL_MODULE_KEYS_FRONTEND],
    },
    validate: {
      name: (v) => (v.trim() ? null : t("superadmin.form.name_required")),
    },
  });

  // Modal ochilganda tahrirlash formasi qayta tiklanadi
  const handleClose = () => {
    createForm.reset();
    editForm.reset();
    onClose();
  };

  // ─── Yaratish ────────────────────────────────────────────────────────────────

  const handleCreate = async (values: CreateFormValues) => {
    try {
      const result = await createEnterprise.mutateAsync({
        name: values.name.trim(),
        inn: values.inn.trim() || null,
        enabled_modules: values.enabled_modules,
        first_admin: {
          full_name: values.admin_full_name.trim(),
          phone: values.admin_phone.trim(),
          password: values.admin_password,
          locale: values.admin_locale,
        },
      });
      notifications.show({
        color: "green",
        message: t("superadmin.messages.enterprise_created", {
          name: result.enterprise.name,
        }),
      });
      handleClose();
    } catch (err) {
      showError(err);
    }
  };

  // ─── Yangilash ───────────────────────────────────────────────────────────────

  const handleEdit = async (values: EditFormValues) => {
    if (!enterprise) return;
    try {
      await updateEnterprise.mutateAsync({
        id: enterprise.id,
        data: {
          name: values.name.trim(),
          enabled_modules: values.enabled_modules,
          version: enterprise.version,
        },
      });
      notifications.show({
        color: "green",
        message: t("superadmin.messages.enterprise_updated"),
      });
      handleClose();
    } catch (err) {
      showError(err);
    }
  };

  const isPending = createEnterprise.isPending || updateEnterprise.isPending;

  // ─── Render ──────────────────────────────────────────────────────────────────

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={
        <Title order={4}>
          {isEdit ? t("superadmin.form.edit_title") : t("superadmin.form.create_title")}
        </Title>
      }
      size="lg"
      closeOnClickOutside={!isPending}
    >
      {isEdit ? (
        // Tahrirlash formasi
        <form onSubmit={editForm.onSubmit((v) => { void handleEdit(v); })}>
          <Stack gap="md">
            <TextInput
              label={t("superadmin.form.name")}
              placeholder={t("superadmin.form.name_placeholder")}
              required
              {...editForm.getInputProps("name")}
            />

            <Stack gap="xs">
              <Text size="sm" fw={500}>{t("superadmin.form.modules")}</Text>
              <SimpleGrid cols={2} spacing="xs">
                {ALL_MODULE_KEYS_FRONTEND.map((key) => (
                  <Checkbox
                    key={key}
                    label={t(`superadmin.modules.${key}`, { defaultValue: key })}
                    checked={editForm.values.enabled_modules.includes(key)}
                    onChange={(e) => {
                      const current = editForm.values.enabled_modules;
                      if (e.currentTarget.checked) {
                        editForm.setFieldValue("enabled_modules", [...current, key]);
                      } else {
                        editForm.setFieldValue(
                          "enabled_modules",
                          current.filter((m) => m !== key),
                        );
                      }
                    }}
                  />
                ))}
              </SimpleGrid>
            </Stack>

            <Group justify="flex-end" mt="sm">
              <Button variant="default" onClick={handleClose} disabled={isPending}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" loading={isPending}>
                {t("common.save")}
              </Button>
            </Group>
          </Stack>
        </form>
      ) : (
        // Yaratish formasi
        <form onSubmit={createForm.onSubmit((v) => { void handleCreate(v); })}>
          <Stack gap="md">
            <TextInput
              label={t("superadmin.form.name")}
              placeholder={t("superadmin.form.name_placeholder")}
              required
              {...createForm.getInputProps("name")}
            />
            <TextInput
              label={t("superadmin.form.inn")}
              placeholder={t("superadmin.form.inn_placeholder")}
              {...createForm.getInputProps("inn")}
            />

            <Stack gap="xs">
              <Text size="sm" fw={500}>{t("superadmin.form.modules")}</Text>
              <SimpleGrid cols={2} spacing="xs">
                {ALL_MODULE_KEYS_FRONTEND.map((key) => (
                  <Checkbox
                    key={key}
                    label={t(`superadmin.modules.${key}`, { defaultValue: key })}
                    checked={createForm.values.enabled_modules.includes(key)}
                    onChange={(e) => {
                      const current = createForm.values.enabled_modules;
                      if (e.currentTarget.checked) {
                        createForm.setFieldValue("enabled_modules", [...current, key]);
                      } else {
                        createForm.setFieldValue(
                          "enabled_modules",
                          current.filter((m) => m !== key),
                        );
                      }
                    }}
                  />
                ))}
              </SimpleGrid>
            </Stack>

            {/* Birinchi admin */}
            <Stack gap="xs">
              <Text size="sm" fw={500} c="blue.7">
                {t("superadmin.form.first_admin_section")}
              </Text>
              <TextInput
                label={t("users.form.full_name")}
                placeholder={t("users.form.full_name_placeholder")}
                required
                {...createForm.getInputProps("admin_full_name")}
              />
              <TextInput
                label={t("users.form.phone")}
                placeholder="+998901234567"
                inputMode="tel"
                required
                {...createForm.getInputProps("admin_phone")}
              />
              <Stack gap={4}>
                <Group gap="xs" align="flex-end">
                  <Box style={{ flex: 1 }}>
                    <PasswordInput
                      label={t("users.form.password")}
                      placeholder={t("users.form.password_placeholder")}
                      required
                      {...createForm.getInputProps("admin_password")}
                    />
                  </Box>
                  <Tooltip label={t("superadmin.form.generate_password")}>
                    <ActionIcon
                      variant="default"
                      size="lg"
                      mb={1}
                      onClick={() => {
                        const pwd = generateStrongPassword();
                        createForm.setFieldValue("admin_password", pwd);
                      }}
                      aria-label={t("superadmin.form.generate_password")}
                    >
                      <IconRefresh size={16} />
                    </ActionIcon>
                  </Tooltip>
                  {createForm.values.admin_password && (
                    <CopyButton value={createForm.values.admin_password} timeout={2000}>
                      {({ copied, copy }) => (
                        <Tooltip
                          label={
                            copied
                              ? t("superadmin.reset_password.copied")
                              : t("superadmin.reset_password.copy")
                          }
                        >
                          <ActionIcon
                            variant="default"
                            size="lg"
                            mb={1}
                            onClick={copy}
                            color={copied ? "teal" : undefined}
                            aria-label={t("superadmin.reset_password.copy")}
                          >
                            {copied ? (
                              <IconCheck size={16} />
                            ) : (
                              <IconCopy size={16} />
                            )}
                          </ActionIcon>
                        </Tooltip>
                      )}
                    </CopyButton>
                  )}
                </Group>
              </Stack>
              <Select
                label={t("users.form.locale")}
                data={[
                  { value: "uz", label: "O'zbekcha" },
                  { value: "ru", label: "Русский" },
                ]}
                allowDeselect={false}
                {...createForm.getInputProps("admin_locale")}
              />
            </Stack>

            <Group justify="flex-end" mt="sm">
              <Button variant="default" onClick={handleClose} disabled={isPending}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" loading={isPending}>
                {t("common.create")}
              </Button>
            </Group>
          </Stack>
        </form>
      )}
    </Modal>
  );
}
