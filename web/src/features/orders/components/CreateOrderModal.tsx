/**
 * CreateOrderModal — yangi buyurtma yaratish modali.
 *
 * T11 himoyasi (MUHIM):
 *   Klient faqat product_id + qty yuboradi. Narx/discount/segment MAYDONLARI YO'Q.
 *   Server narxni katalogdan avtomatik hisoblaydi.
 *
 * Xususiyatlar:
 * - Do'kon tanlash (store_id)
 * - Mahsulot qo'shish (product_id + qty) — ko'p qator
 * - Narx ko'rsatilmaydi (server hisoblaydi)
 * - RBAC: <Can permission="orders:create">
 * - i18n uz/ru
 */

import {
  ActionIcon,
  Button,
  Group,
  Modal,
  NumberInput,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { IconPlus, IconTrash } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import { useCreateOrder } from "../api/ordersApi";
import { useApiError } from "@/hooks/useApiError";
import { notifications } from "@mantine/notifications";
import type { OrderLineIn, OrderMode } from "../types";

interface CreateOrderModalProps {
  opened: boolean;
  onClose: () => void;
}

interface OrderLineFormItem {
  product_id: string;
  qty: number;
}

interface CreateOrderFormValues {
  store_id: string;
  mode: OrderMode;
  lines: OrderLineFormItem[];
}

export function CreateOrderModal({ opened, onClose }: CreateOrderModalProps) {
  const { t } = useTranslation();
  const { showError } = useApiError();
  const createOrder = useCreateOrder();

  const form = useForm<CreateOrderFormValues>({
    initialValues: {
      store_id: "",
      mode: "oddiy",
      lines: [{ product_id: "", qty: 1 }],
    },
    validate: {
      store_id: (v) =>
        v.trim().length === 0 ? t("orders.create.store_required") : null,
      lines: {
        product_id: (v) =>
          v.trim().length === 0 ? t("orders.create.product_required") : null,
        qty: (v) =>
          v <= 0 ? t("orders.create.qty_positive") : null,
      },
    },
  });

  const handleClose = () => {
    form.reset();
    onClose();
  };

  const handleSubmit = async (values: CreateOrderFormValues) => {
    // T11: faqat product_id + qty — narx/discount YUBORILMAYDI
    const lines: OrderLineIn[] = values.lines.map((l) => ({
      product_id: l.product_id.trim(),
      qty: String(l.qty),
    }));

    try {
      await createOrder.mutateAsync({
        store_id: values.store_id.trim(),
        mode: values.mode,
        lines,
      });
      notifications.show({
        color: "green",
        message: t("orders.messages.created"),
      });
      handleClose();
    } catch (err) {
      showError(err);
    }
  };

  const addLine = () => {
    form.insertListItem("lines", { product_id: "", qty: 1 });
  };

  const removeLine = (index: number) => {
    if (form.values.lines.length > 1) {
      form.removeListItem("lines", index);
    }
  };

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={
        <Text fw={600}>{t("orders.create.title")}</Text>
      }
      size="lg"
      centered
    >
      <form onSubmit={form.onSubmit((v) => { void handleSubmit(v); })}>
        <Stack gap="sm">
          {/* Do'kon ID */}
          <TextInput
            label={t("orders.create.store_id")}
            placeholder={t("orders.create.store_id_placeholder")}
            required
            {...form.getInputProps("store_id")}
          />

          {/* Buyurtma turi */}
          <Select
            label={t("orders.create.mode")}
            data={[
              { value: "oddiy", label: t("orders.mode.oddiy") },
              { value: "bozor", label: t("orders.mode.bozor") },
            ]}
            {...form.getInputProps("mode")}
          />

          {/* Qatorlar — faqat product_id + qty (T11) */}
          <Text size="sm" fw={500}>
            {t("orders.create.lines")}
          </Text>

          {/* MUHIM: Narx/discount maydonlari ataylab yo'q — server hisoblaydi (T11) */}
          <Table.ScrollContainer minWidth={400}>
            <Table withTableBorder>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t("orders.create.product_id")}</Table.Th>
                  <Table.Th w={120}>{t("orders.create.qty")}</Table.Th>
                  <Table.Th w={50}></Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {form.values.lines.map((_, index) => (
                  <Table.Tr key={index}>
                    <Table.Td>
                      <TextInput
                        placeholder={t("orders.create.product_id_placeholder")}
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
                        aria-label={t("common.delete")}
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
            {t("orders.create.add_line")}
          </Button>

          {/* Server narx hisoblashi haqida izoh */}
          <Text size="xs" c="dimmed">
            {t("orders.create.price_note")}
          </Text>

          <Group justify="flex-end" mt="md">
            <Button
              variant="subtle"
              onClick={handleClose}
              disabled={createOrder.isPending}
            >
              {t("common.cancel")}
            </Button>
            <Button type="submit" loading={createOrder.isPending}>
              {t("orders.create.submit")}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
