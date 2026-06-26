/**
 * OrderTemplatesModal — buyurtma shablonlarini boshqarish modali.
 *
 * Xususiyatlar:
 * - Shablonlar ro'yxati (nomi, do'kon, qatorlar soni)
 * - Yangi shablon yaratish (name + store_id + lines)
 * - Shablon o'chirish (ConfirmDeleteModal bilan)
 * - "Shablondan buyurtma" (apply) — buyurtmalar ro'yxatini yangilaydi
 * - RBAC: <Can permission="orders:create"> yaratish/apply tugmalari
 * - i18n: inline t("kalit", { defaultValue: "..." }) — json fayllar tahrirlanmaydi
 *
 * T11 himoyasi: lines faqat product_id + qty (narx/discount yo'q).
 */

import {
  ActionIcon,
  Button,
  Card,
  Divider,
  Group,
  Loader,
  Modal,
  NumberInput,
  Stack,
  Table,
  Text,
  TextInput,
  Tooltip,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { IconPlus, IconTemplate, IconTrash } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import { Can } from "@/rbac/Can";
import { useApiError } from "@/hooks/useApiError";
import { ConfirmDeleteModal } from "@/components/ConfirmDeleteModal";
import {
  useTemplates,
  useCreateTemplate,
  useDeleteTemplate,
  useApplyTemplate,
} from "../api/ordersApi";
import type { OrderTemplateOut, TemplateLineIn } from "../types";

// ─── Props ────────────────────────────────────────────────────────────────────

interface OrderTemplatesModalProps {
  opened: boolean;
  onClose: () => void;
}

// ─── Forma tipi ───────────────────────────────────────────────────────────────

interface TemplateLineFormItem {
  product_id: string;
  qty: number;
}

interface CreateTemplateFormValues {
  name: string;
  store_id: string;
  lines: TemplateLineFormItem[];
}

// ─── Komponent ────────────────────────────────────────────────────────────────

export function OrderTemplatesModal({
  opened,
  onClose,
}: OrderTemplatesModalProps) {
  const { t } = useTranslation();
  const { showError } = useApiError();

  // API hooks
  const { data: templates, isLoading } = useTemplates();
  const createTemplate = useCreateTemplate();
  const deleteTemplate = useDeleteTemplate();
  const applyTemplate = useApplyTemplate();

  // Yaratish formasi ko'rinishi
  const [createOpened, { open: openCreate, close: closeCreate }] =
    useDisclosure(false);

  // O'chirish tasdiqlash
  const [deleteTarget, setDeleteTarget] = useState<OrderTemplateOut | null>(
    null,
  );
  const [deleteOpened, { open: openDelete, close: closeDelete }] =
    useDisclosure(false);

  // Apply pending tracking
  const [applyingId, setApplyingId] = useState<string | null>(null);

  // ─── Yaratish formasi ───────────────────────────────────────────────────────

  const form = useForm<CreateTemplateFormValues>({
    initialValues: {
      name: "",
      store_id: "",
      lines: [{ product_id: "", qty: 1 }],
    },
    validate: {
      name: (v) =>
        v.trim().length === 0
          ? t("orders.templates.name_required", {
              defaultValue: "Shablon nomi majburiy",
            })
          : null,
      store_id: (v) =>
        v.trim().length === 0
          ? t("orders.templates.store_required", {
              defaultValue: "Do'kon ID majburiy",
            })
          : null,
      lines: {
        product_id: (v) =>
          v.trim().length === 0
            ? t("orders.create.product_required", {
                defaultValue: "Mahsulot ID majburiy",
              })
            : null,
        qty: (v) =>
          v <= 0
            ? t("orders.create.qty_positive", {
                defaultValue: "Miqdor 0 dan katta bo'lishi kerak",
              })
            : null,
      },
    },
  });

  const handleCreateSubmit = async (values: CreateTemplateFormValues) => {
    const lines: TemplateLineIn[] = values.lines.map((l) => ({
      product_id: l.product_id.trim(),
      qty: String(l.qty),
    }));

    try {
      await createTemplate.mutateAsync({
        name: values.name.trim(),
        store_id: values.store_id.trim(),
        lines,
      });
      notifications.show({
        color: "green",
        message: t("orders.templates.created", {
          defaultValue: "Shablon muvaffaqiyatli yaratildi",
        }),
      });
      form.reset();
      closeCreate();
    } catch (err) {
      showError(err);
    }
  };

  const handleCreateClose = () => {
    form.reset();
    closeCreate();
  };

  const addLine = () => {
    form.insertListItem("lines", { product_id: "", qty: 1 });
  };

  const removeLine = (index: number) => {
    if (form.values.lines.length > 1) {
      form.removeListItem("lines", index);
    }
  };

  // ─── O'chirish ──────────────────────────────────────────────────────────────

  const handleDeleteClick = (template: OrderTemplateOut) => {
    setDeleteTarget(template);
    openDelete();
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    try {
      await deleteTemplate.mutateAsync(deleteTarget.id);
      notifications.show({
        color: "orange",
        message: t("orders.templates.deleted", {
          defaultValue: "Shablon o'chirildi",
        }),
      });
      closeDelete();
      setDeleteTarget(null);
    } catch (err) {
      showError(err);
    }
  };

  // ─── Apply ──────────────────────────────────────────────────────────────────

  const handleApply = async (template: OrderTemplateOut) => {
    setApplyingId(template.id);
    try {
      await applyTemplate.mutateAsync(template.id);
      notifications.show({
        color: "green",
        message: t("orders.templates.applied", {
          defaultValue: "Shablondan buyurtma yaratildi",
        }),
      });
    } catch (err) {
      showError(err);
    } finally {
      setApplyingId(null);
    }
  };

  // ─── Render ─────────────────────────────────────────────────────────────────

  return (
    <>
      <Modal
        opened={opened}
        onClose={onClose}
        title={
          <Group gap="sm">
            <IconTemplate size={18} />
            <Text fw={600}>
              {t("orders.templates.title", {
                defaultValue: "Buyurtma shablonlari",
              })}
            </Text>
          </Group>
        }
        size="xl"
        centered
      >
        <Stack gap="md">
          {/* Yangi shablon tugmasi */}
          <Can permission="orders:create">
            <Group justify="flex-end">
              <Button
                leftSection={<IconPlus size={14} />}
                size="sm"
                onClick={openCreate}
              >
                {t("orders.templates.create_btn", {
                  defaultValue: "Yangi shablon",
                })}
              </Button>
            </Group>
          </Can>

          {/* Shablonlar ro'yxati */}
          {isLoading ? (
            <Group justify="center" py="xl">
              <Loader size="sm" />
              <Text c="dimmed">{t("common.loading", { defaultValue: "Yuklanmoqda..." })}</Text>
            </Group>
          ) : !templates?.length ? (
            <Text c="dimmed" ta="center" py="xl">
              {t("orders.templates.empty", {
                defaultValue: "Hozircha shablonlar yo'q",
              })}
            </Text>
          ) : (
            <Stack gap="sm">
              {templates.map((tmpl) => (
                <Card key={tmpl.id} withBorder padding="sm" radius="sm">
                  <Group justify="space-between" wrap="nowrap">
                    <Stack gap={2}>
                      <Text fw={600} size="sm">
                        {tmpl.name}
                      </Text>
                      <Text size="xs" c="dimmed" ff="monospace">
                        {t("orders.table.store", { defaultValue: "Do'kon" })}:{" "}
                        {tmpl.store_id.slice(0, 8)}...
                      </Text>
                      <Text size="xs" c="dimmed">
                        {t("orders.templates.lines_count", {
                          count: tmpl.lines.length,
                          defaultValue: `${tmpl.lines.length} ta qator`,
                        })}
                      </Text>
                    </Stack>

                    <Group gap={6} wrap="nowrap">
                      <Can permission="orders:create">
                        <Tooltip
                          label={t("orders.templates.apply_tooltip", {
                            defaultValue: "Shablondan buyurtma yaratish",
                          })}
                        >
                          <Button
                            size="xs"
                            variant="light"
                            loading={applyingId === tmpl.id}
                            onClick={() => {
                              void handleApply(tmpl);
                            }}
                          >
                            {t("orders.templates.apply_btn", {
                              defaultValue: "Buyurtma",
                            })}
                          </Button>
                        </Tooltip>
                      </Can>

                      <Can permission="orders:create">
                        <Tooltip
                          label={t("common.delete", {
                            defaultValue: "O'chirish",
                          })}
                        >
                          <ActionIcon
                            variant="subtle"
                            color="red"
                            size="sm"
                            onClick={() => handleDeleteClick(tmpl)}
                          >
                            <IconTrash size={14} />
                          </ActionIcon>
                        </Tooltip>
                      </Can>
                    </Group>
                  </Group>
                </Card>
              ))}
            </Stack>
          )}

          <Group justify="flex-end">
            <Button variant="subtle" onClick={onClose}>
              {t("common.close", { defaultValue: "Yopish" })}
            </Button>
          </Group>
        </Stack>
      </Modal>

      {/* Yangi shablon yaratish sub-modal */}
      <Modal
        opened={createOpened}
        onClose={handleCreateClose}
        title={
          <Text fw={600}>
            {t("orders.templates.create_title", {
              defaultValue: "Yangi shablon yaratish",
            })}
          </Text>
        }
        size="lg"
        centered
        zIndex={300}
      >
        <form
          onSubmit={form.onSubmit((v) => {
            void handleCreateSubmit(v);
          })}
        >
          <Stack gap="sm">
            {/* Shablon nomi */}
            <TextInput
              label={t("orders.templates.name", {
                defaultValue: "Shablon nomi",
              })}
              placeholder={t("orders.templates.name_placeholder", {
                defaultValue: "Masalan: Haftalik standart buyurtma",
              })}
              required
              {...form.getInputProps("name")}
            />

            {/* Do'kon ID */}
            <TextInput
              label={t("orders.create.store_id", { defaultValue: "Do'kon ID" })}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              description={t("orders.create.store_id_hint", {
                defaultValue: "UUID formatida (majburiy)",
              })}
              required
              {...form.getInputProps("store_id")}
            />

            <Divider
              label={t("orders.create.lines", { defaultValue: "Mahsulotlar" })}
              labelPosition="left"
            />

            {/* Qatorlar — faqat product_id + qty (T11) */}
            <Table.ScrollContainer minWidth={400}>
              <Table withTableBorder>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>
                      {t("orders.create.product_id", {
                        defaultValue: "Mahsulot ID",
                      })}
                    </Table.Th>
                    <Table.Th w={120}>
                      {t("orders.create.qty", { defaultValue: "Miqdor" })}
                    </Table.Th>
                    <Table.Th w={50}></Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {form.values.lines.map((_, index) => (
                    <Table.Tr key={index}>
                      <Table.Td>
                        <TextInput
                          placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                          size="xs"
                          {...form.getInputProps(`lines.${index}.product_id`)}
                        />
                      </Table.Td>
                      <Table.Td>
                        <NumberInput
                          min={0.0001}
                          step={1}
                          decimalScale={4}
                          size="xs"
                          {...form.getInputProps(`lines.${index}.qty`)}
                        />
                      </Table.Td>
                      <Table.Td>
                        <ActionIcon
                          variant="subtle"
                          color="red"
                          size="sm"
                          disabled={form.values.lines.length <= 1}
                          onClick={() => removeLine(index)}
                          aria-label={t("common.delete", {
                            defaultValue: "O'chirish",
                          })}
                        >
                          <IconTrash size={14} />
                        </ActionIcon>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>

            <Button
              variant="subtle"
              leftSection={<IconPlus size={14} />}
              size="xs"
              onClick={addLine}
            >
              {t("orders.create.add_line", { defaultValue: "Qator qo'shish" })}
            </Button>

            <Group justify="flex-end" mt="md">
              <Button
                variant="subtle"
                onClick={handleCreateClose}
                disabled={createTemplate.isPending}
              >
                {t("common.cancel", { defaultValue: "Bekor qilish" })}
              </Button>
              <Button type="submit" loading={createTemplate.isPending}>
                {t("orders.templates.save_btn", { defaultValue: "Saqlash" })}
              </Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      {/* O'chirish tasdiqlash */}
      <ConfirmDeleteModal
        opened={deleteOpened}
        onClose={() => {
          closeDelete();
          setDeleteTarget(null);
        }}
        onConfirm={() => {
          void handleDeleteConfirm();
        }}
        title={t("orders.templates.delete_title", {
          defaultValue: "Shablonni o'chirish",
        })}
        message={t("orders.templates.delete_confirm", {
          name: deleteTarget?.name ?? "",
          defaultValue: `"${deleteTarget?.name ?? ""}" shablonini o'chirishni tasdiqlaysizmi?`,
        })}
        loading={deleteTemplate.isPending}
      />
    </>
  );
}
