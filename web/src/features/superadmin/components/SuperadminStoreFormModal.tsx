/**
 * SuperadminStoreFormModal — platforma do'kon yaratish modali.
 *
 * name — majburiy.
 * owner_name, phone, address, gps_lat, gps_lng, inn, inps — ixtiyoriy.
 * enterprise_id server tomonidan avtomatik o'rnatiladi.
 */

import {
  Button,
  Group,
  Modal,
  NumberInput,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useTranslation } from "react-i18next";
import { notifications } from "@mantine/notifications";
import { useCreateSuperadminStore } from "../api/superadminApi";
import { useApiError } from "@/hooks/useApiError";

// ─── Props ────────────────────────────────────────────────────────────────────

interface SuperadminStoreFormModalProps {
  opened: boolean;
  onClose: () => void;
}

// ─── Forma qiymatlari ─────────────────────────────────────────────────────────

interface StoreFormValues {
  name: string;
  owner_name: string;
  phone: string;
  address: string;
  gps_lat: number | string;
  gps_lng: number | string;
  inn: string;
  inps: string;
}

// ─── Komponent ────────────────────────────────────────────────────────────────

export function SuperadminStoreFormModal({
  opened,
  onClose,
}: SuperadminStoreFormModalProps) {
  const { t } = useTranslation();
  const { showError } = useApiError();
  const createStore = useCreateSuperadminStore();

  const form = useForm<StoreFormValues>({
    initialValues: {
      name: "",
      owner_name: "",
      phone: "",
      address: "",
      gps_lat: "",
      gps_lng: "",
      inn: "",
      inps: "",
    },
    validate: {
      name: (v) =>
        v.trim()
          ? null
          : t("superadmin.stores.form.name_required", {
              defaultValue: "Do'kon nomi majburiy",
            }),
      gps_lat: (v) => {
        if (v === "" || v === null || v === undefined) return null;
        const n = Number(v);
        if (isNaN(n) || n < -90 || n > 90)
          return t("customers.form.gps_lat_invalid");
        return null;
      },
      gps_lng: (v) => {
        if (v === "" || v === null || v === undefined) return null;
        const n = Number(v);
        if (isNaN(n) || n < -180 || n > 180)
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
      await createStore.mutateAsync({
        name: values.name.trim(),
        owner_name: values.owner_name.trim() || null,
        phone: values.phone.trim() || null,
        address: values.address.trim() || null,
        gps_lat:
          values.gps_lat !== "" && values.gps_lat !== undefined
            ? Number(values.gps_lat)
            : null,
        gps_lng:
          values.gps_lng !== "" && values.gps_lng !== undefined
            ? Number(values.gps_lng)
            : null,
        inn: values.inn.trim() || null,
        inps: values.inps.trim() || null,
      });
      notifications.show({
        color: "green",
        message: t("superadmin.stores.messages.created", {
          defaultValue: "Platforma do'kon muvaffaqiyatli yaratildi",
          name: values.name.trim(),
        }),
      });
      handleClose();
    } catch (err) {
      showError(err);
    }
  };

  const isPending = createStore.isPending;

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={
        <Title order={4}>
          {t("superadmin.stores.form.create_title", {
            defaultValue: "Platforma do'kon qo'shish",
          })}
        </Title>
      }
      size="lg"
      closeOnClickOutside={!isPending}
    >
      <form onSubmit={form.onSubmit((v) => { void handleSubmit(v); })}>
        <Stack gap="md">
          <TextInput
            label={t("superadmin.stores.form.name", {
              defaultValue: "Do'kon nomi",
            })}
            placeholder={t("superadmin.stores.form.name_placeholder", {
              defaultValue: "Do'kon nomini kiriting",
            })}
            required
            {...form.getInputProps("name")}
          />

          <SimpleGrid cols={2} spacing="sm">
            <TextInput
              label={t("customers.form.owner_name")}
              placeholder={t("customers.form.owner_name_placeholder")}
              {...form.getInputProps("owner_name")}
            />
            <TextInput
              label={t("customers.form.phone")}
              placeholder="+998901234567"
              inputMode="tel"
              {...form.getInputProps("phone")}
            />
          </SimpleGrid>

          <TextInput
            label={t("customers.form.address")}
            placeholder={t("customers.form.address_placeholder")}
            {...form.getInputProps("address")}
          />

          <SimpleGrid cols={2} spacing="sm">
            <NumberInput
              label={t("customers.form.gps_lat")}
              placeholder="41.2995"
              decimalScale={6}
              min={-90}
              max={90}
              hideControls
              {...form.getInputProps("gps_lat")}
            />
            <NumberInput
              label={t("customers.form.gps_lng")}
              placeholder="69.2401"
              decimalScale={6}
              min={-180}
              max={180}
              hideControls
              {...form.getInputProps("gps_lng")}
            />
          </SimpleGrid>

          <SimpleGrid cols={2} spacing="sm">
            <TextInput
              label={t("customers.form.inn")}
              placeholder="123456789"
              {...form.getInputProps("inn")}
            />
            <TextInput
              label={t("customers.form.inps", { defaultValue: "INPS" })}
              placeholder="INPS"
              {...form.getInputProps("inps")}
            />
          </SimpleGrid>

          {/* Izoh: enterprise_id server o'rnatadi */}
          <Text size="xs" c="dimmed">
            {t("superadmin.stores.form.enterprise_note", {
              defaultValue:
                "enterprise_id server tomonidan avtomatik o'rnatiladi.",
            })}
          </Text>

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
    </Modal>
  );
}
