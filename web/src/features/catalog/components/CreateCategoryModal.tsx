/**
 * CreateCategoryModal — yangi kategoriya yaratish modali.
 *
 * POST /catalog/categories
 * Body: { name_uz, name_ru?, parent_id?, is_active? }
 */

import {
  Button,
  Checkbox,
  Group,
  Modal,
  Select,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useTranslation } from "react-i18next";
import { useCategories, useCreateCategory } from "../api/catalogApi";
import { useApiError } from "@/hooks/useApiError";

interface CreateCategoryModalProps {
  opened: boolean;
  onClose: () => void;
}

interface CategoryFormValues {
  name_uz: string;
  name_ru: string;
  parent_id: string;
  is_active: boolean;
}

export function CreateCategoryModal({
  opened,
  onClose,
}: CreateCategoryModalProps) {
  const { t } = useTranslation();
  const { showError, showSuccess } = useApiError();
  const createCategory = useCreateCategory();
  const { data: categories = [] } = useCategories();

  const form = useForm<CategoryFormValues>({
    initialValues: {
      name_uz: "",
      name_ru: "",
      parent_id: "",
      is_active: true,
    },
    validate: {
      name_uz: (v) =>
        v.trim().length === 0
          ? t("catalog.category_form.name_required", { defaultValue: "Nom (UZ) majburiy" })
          : null,
    },
  });

  const handleClose = () => {
    form.reset();
    onClose();
  };

  const handleSubmit = async (values: CategoryFormValues) => {
    try {
      await createCategory.mutateAsync({
        name_uz: values.name_uz.trim(),
        name_ru: values.name_ru.trim() || undefined,
        parent_id: values.parent_id || null,
        is_active: values.is_active,
      });
      showSuccess("catalog.messages.category_created");
      handleClose();
    } catch (err) {
      showError(err);
    }
  };

  const parentOptions = categories.map((c) => ({
    value: c.id,
    label: c.name_uz,
  }));

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={
        <Text fw={600}>
          {t("catalog.category_form.title", { defaultValue: "Kategoriya qo'shish" })}
        </Text>
      }
      size="sm"
      centered
    >
      <form onSubmit={form.onSubmit((v) => { void handleSubmit(v); })}>
        <Stack gap="sm">
          <TextInput
            label={t("catalog.category_form.name_uz", { defaultValue: "Nomi (UZ)" })}
            placeholder={t("catalog.category_form.name_uz_placeholder", { defaultValue: "Masalan: Non mahsulotlari" })}
            required
            {...form.getInputProps("name_uz")}
          />
          <TextInput
            label={t("catalog.category_form.name_ru", { defaultValue: "Nomi (RU)" })}
            placeholder={t("catalog.category_form.name_ru_placeholder", { defaultValue: "Например: Хлебобулочные изделия" })}
            {...form.getInputProps("name_ru")}
          />
          <Select
            label={t("catalog.category_form.parent", { defaultValue: "Yuqori kategoriya (ixtiyoriy)" })}
            placeholder={t("catalog.category_form.parent_placeholder", { defaultValue: "Tanlang yoki bo'sh qoldiring" })}
            data={parentOptions}
            clearable
            {...form.getInputProps("parent_id")}
          />
          <Checkbox
            label={t("catalog.category_form.is_active", { defaultValue: "Faol" })}
            {...form.getInputProps("is_active", { type: "checkbox" })}
          />
          <Group justify="flex-end" mt="md">
            <Button
              variant="subtle"
              onClick={handleClose}
              disabled={createCategory.isPending}
            >
              {t("common.cancel")}
            </Button>
            <Button type="submit" loading={createCategory.isPending}>
              {t("common.create")}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
