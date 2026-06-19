/**
 * StoreFormModal — do'kon yaratish / tahrirlash modal.
 *
 * RBAC: customers:create (yangi) / customers:edit (tahrirlash).
 * PII maydonlar: INN, INPS, owner_name, phone — backend shifrlaydi.
 * GPS: kenglik/uzunlik ixtiyoriy.
 * i18n uz/ru.
 */

import {
  Button,
  Group,
  Modal,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useTranslation } from "react-i18next";
import { useCreateStore, useUpdateStore } from "../api/customersApi";
import { useApiError } from "@/hooks/useApiError";
import type { StoreOut } from "@/api/types";

// ─── Props ────────────────────────────────────────────────────────────────────

interface StoreFormModalProps {
  opened: boolean;
  onClose: () => void;
  store?: StoreOut;
}

// ─── Forma qiymatlari ─────────────────────────────────────────────────────────

interface StoreFormValues {
  name: string;
  inn: string;
  inps: string;
  owner_name: string;
  phone: string;
  address: string;
  gps_lat: string;
  gps_lng: string;
  credit_limit: string;
}

// ─── Komponent ────────────────────────────────────────────────────────────────

export function StoreFormModal({
  opened,
  onClose,
  store,
}: StoreFormModalProps) {
  const { t } = useTranslation();
  const { showError, showSuccess } = useApiError();
  const isEdit = Boolean(store);

  const createStore = useCreateStore();
  const updateStore = useUpdateStore();

  const form = useForm<StoreFormValues>({
    initialValues: {
      name: store?.name ?? "",
      inn: store?.inn ?? "",
      inps: store?.inps ?? "",
      owner_name: store?.owner_name ?? "",
      phone: store?.phone ?? "",
      address: store?.address ?? "",
      gps_lat: store?.gps_lat != null ? String(store.gps_lat) : "",
      gps_lng: store?.gps_lng != null ? String(store.gps_lng) : "",
      credit_limit: store?.credit_limit != null ? String(store.credit_limit) : "",
    },
    validate: {
      name: (v) =>
        v.trim().length === 0 ? t("customers.form.name_required") : null,
      phone: (v) => {
        if (!v) return null; // ixtiyoriy
        const cleaned = v.replace(/\D/g, "");
        return cleaned.length < 9 ? t("customers.form.phone_invalid") : null;
      },
      inn: (v) => {
        if (!v) return null;
        if (!/^\d{9}$/.test(v.trim())) return t("customers.form.inn_invalid");
        return null;
      },
      gps_lat: (v) => {
        if (!v) return null;
        const num = parseFloat(v);
        if (isNaN(num) || num < -90 || num > 90)
          return t("customers.form.gps_lat_invalid");
        return null;
      },
      gps_lng: (v) => {
        if (!v) return null;
        const num = parseFloat(v);
        if (isNaN(num) || num < -180 || num > 180)
          return t("customers.form.gps_lng_invalid");
        return null;
      },
    },
  });

  const handleClose = () => {
    form.reset();
    onClose();
  };

  const handleSubmit = async (values: StoreFormValues) => {
    try {
      if (isEdit && store) {
        await updateStore.mutateAsync({
          id: store.id,
          data: {
            name: values.name,
            inn: values.inn || null,
            inps: values.inps || null,
            owner_name: values.owner_name || null,
            phone: values.phone || null,
            address: values.address || null,
            gps_lat: values.gps_lat || null,
            gps_lng: values.gps_lng || null,
            credit_limit: values.credit_limit || null,
            version: store.version,
          },
        });
        showSuccess("customers.messages.store_updated");
      } else {
        await createStore.mutateAsync({
          name: values.name,
          inn: values.inn || null,
          inps: values.inps || null,
          owner_name: values.owner_name || null,
          phone: values.phone || null,
          address: values.address || null,
          gps_lat: values.gps_lat || null,
          gps_lng: values.gps_lng || null,
          credit_limit: values.credit_limit || null,
        });
        showSuccess("customers.messages.store_created");
      }
      handleClose();
    } catch (err) {
      showError(err);
    }
  };

  const isPending = createStore.isPending || updateStore.isPending;

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={
        <Text fw={600}>
          {isEdit ? t("customers.form.edit_title") : t("customers.form.create_title")}
        </Text>
      }
      size="lg"
      centered
    >
      <form onSubmit={form.onSubmit((v) => { void handleSubmit(v); })}>
        <Stack gap="sm">
          <TextInput
            label={t("customers.form.name")}
            placeholder={t("customers.form.name_placeholder")}
            required
            {...form.getInputProps("name")}
          />

          <Group grow>
            {/* PII maydon — backend shifrlaydi */}
            <TextInput
              label={t("customers.form.inn")}
              placeholder="123456789"
              description={t("customers.form.inn_hint")}
              {...form.getInputProps("inn")}
            />
            <TextInput
              label={t("customers.form.inps")}
              placeholder="12345678901234"
              {...form.getInputProps("inps")}
            />
          </Group>

          <Group grow>
            <TextInput
              label={t("customers.form.owner_name")}
              placeholder={t("customers.form.owner_name_placeholder")}
              {...form.getInputProps("owner_name")}
            />
            <TextInput
              label={t("customers.form.phone")}
              placeholder="998901234567"
              {...form.getInputProps("phone")}
            />
          </Group>

          <TextInput
            label={t("customers.form.address")}
            placeholder={t("customers.form.address_placeholder")}
            {...form.getInputProps("address")}
          />

          <Group grow>
            <TextInput
              label={t("customers.form.gps_lat")}
              placeholder="41.299496"
              {...form.getInputProps("gps_lat")}
            />
            <TextInput
              label={t("customers.form.gps_lng")}
              placeholder="69.240073"
              {...form.getInputProps("gps_lng")}
            />
          </Group>

          <TextInput
            label={t("customers.form.credit_limit")}
            placeholder="5000000"
            description={t("customers.form.credit_limit_hint")}
            {...form.getInputProps("credit_limit")}
          />

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
