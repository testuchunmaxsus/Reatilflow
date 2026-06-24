/**
 * UserFormModal — foydalanuvchi yaratish / tahrirlash modal.
 *
 * Yaratish: full_name, phone, password, role, branch_id, locale.
 * Tahrirlash: full_name, phone, role, branch_id, locale (password emas).
 * RBAC: faqat administrator (backend ham tekshiradi).
 * Optimistik lock: tahrirlashda version majburiy (PATCH).
 * i18n uz/ru.
 */

import {
  Button,
  Group,
  Modal,
  PasswordInput,
  Select,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useTranslation } from "react-i18next";
import { useCreateUser, useUpdateUser } from "../api/usersApi";
import { useApiError } from "@/hooks/useApiError";
import type { UserOut, UserRole } from "../types";

// ─── Props ────────────────────────────────────────────────────────────────────

interface UserFormModalProps {
  opened: boolean;
  onClose: () => void;
  user?: UserOut;
}

// ─── Forma qiymatlari ─────────────────────────────────────────────────────────

interface UserFormValues {
  full_name: string;
  phone: string;
  password: string;
  role: UserRole | "";
  branch_id: string;
  locale: "uz" | "ru";
}

// ─── Rollar ───────────────────────────────────────────────────────────────────

const ROLE_VALUES: UserRole[] = [
  "administrator",
  "agent",
  "courier",
  "accountant",
  "store",
];

// ─── Komponent ────────────────────────────────────────────────────────────────

export function UserFormModal({ opened, onClose, user }: UserFormModalProps) {
  const { t } = useTranslation();
  const { showError, showSuccess } = useApiError();
  const isEdit = Boolean(user);

  const createUser = useCreateUser();
  const updateUser = useUpdateUser();

  const roleOptions = ROLE_VALUES.map((r) => ({
    value: r,
    label: t(`common.role.${r}`),
  }));

  const localeOptions = [
    { value: "uz", label: "O'zbek" },
    { value: "ru", label: "Русский" },
  ];

  const form = useForm<UserFormValues>({
    initialValues: {
      full_name: user?.full_name ?? "",
      phone: user?.phone ?? "",
      password: "",
      role: user?.role ?? "",
      branch_id: user?.branch_id ?? "",
      locale: user?.locale ?? "uz",
    },
    validate: {
      full_name: (v) =>
        v.trim().length === 0 ? t("users.form.full_name_required") : null,
      phone: (v) => {
        const cleaned = v.replace(/\D/g, "");
        return cleaned.length < 7 ? t("users.form.phone_invalid") : null;
      },
      password: (v) => {
        if (isEdit) return null; // tahrirlashda parol ixtiyoriy
        return v.length < 6 ? t("users.form.password_min") : null;
      },
      role: (v) =>
        !v ? t("users.form.role_required") : null,
      branch_id: (v) => {
        // Ixtiyoriy: bo'sh bo'lsa "barcha filiallar" (null). To'ldirilsa — UUID bo'lishi shart
        // (aks holda backend 422 "uuid_parsing" beradi).
        if (!v.trim()) return null;
        const isUuid =
          /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
            v.trim(),
          );
        return isUuid
          ? null
          : t("users.form.branch_invalid", {
              defaultValue: "Filial ID UUID formatida bo'lishi kerak (yoki bo'sh qoldiring)",
            });
      },
    },
  });

  const handleClose = () => {
    form.reset();
    onClose();
  };

  const handleSubmit = async (values: UserFormValues) => {
    try {
      if (isEdit && user) {
        await updateUser.mutateAsync({
          id: user.id,
          data: {
            full_name: values.full_name,
            phone: values.phone,
            role: values.role as UserRole,
            branch_id: values.branch_id || null,
            locale: values.locale,
            version: user.version,
          },
        });
        showSuccess("users.messages.user_updated");
      } else {
        await createUser.mutateAsync({
          full_name: values.full_name,
          phone: values.phone,
          password: values.password,
          role: values.role as UserRole,
          branch_id: values.branch_id || null,
          locale: values.locale,
        });
        showSuccess("users.messages.user_created");
      }
      handleClose();
    } catch (err) {
      showError(err);
    }
  };

  const isPending = createUser.isPending || updateUser.isPending;

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={
        <Text fw={600}>
          {isEdit ? t("users.form.edit_title") : t("users.form.create_title")}
        </Text>
      }
      size="md"
      centered
    >
      <form onSubmit={form.onSubmit((v) => { void handleSubmit(v); })}>
        <Stack gap="sm">
          <TextInput
            label={t("users.form.full_name")}
            placeholder={t("users.form.full_name_placeholder")}
            required
            {...form.getInputProps("full_name")}
          />

          <TextInput
            label={t("users.form.phone")}
            placeholder="998901234567"
            description={t("users.form.phone_hint")}
            required
            {...form.getInputProps("phone")}
          />

          {!isEdit && (
            <PasswordInput
              label={t("users.form.password")}
              placeholder={t("users.form.password_placeholder")}
              description={t("users.form.password_hint")}
              required
              {...form.getInputProps("password")}
            />
          )}

          <Select
            label={t("users.form.role")}
            placeholder={t("users.form.role_placeholder")}
            data={roleOptions}
            required
            {...form.getInputProps("role")}
          />

          <Group grow>
            <TextInput
              label={t("users.form.branch_id")}
              placeholder="UUID (ixtiyoriy)"
              description={t("users.form.branch_id_hint")}
              {...form.getInputProps("branch_id")}
            />
            <Select
              label={t("users.form.locale")}
              data={localeOptions}
              {...form.getInputProps("locale")}
              allowDeselect={false}
            />
          </Group>

          <Group justify="flex-end" mt="md">
            <Button variant="subtle" onClick={handleClose} disabled={isPending}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" loading={isPending}>
              {isEdit ? t("common.save") : t("common.create")}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
