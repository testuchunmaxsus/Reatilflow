/**
 * CreateSegmentModal — yangi narx segmenti yaratish modali.
 *
 * POST /catalog/price-segments
 * Body: { name }
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
import { useCreateSegment } from "../api/catalogApi";
import { useApiError } from "@/hooks/useApiError";

interface CreateSegmentModalProps {
  opened: boolean;
  onClose: () => void;
}

interface SegmentFormValues {
  name: string;
}

export function CreateSegmentModal({
  opened,
  onClose,
}: CreateSegmentModalProps) {
  const { t } = useTranslation();
  const { showError, showSuccess } = useApiError();
  const createSegment = useCreateSegment();

  const form = useForm<SegmentFormValues>({
    initialValues: {
      name: "",
    },
    validate: {
      name: (v) =>
        v.trim().length === 0
          ? t("catalog.segment_form.name_required", { defaultValue: "Segment nomi majburiy" })
          : null,
    },
  });

  const handleClose = () => {
    form.reset();
    onClose();
  };

  const handleSubmit = async (values: SegmentFormValues) => {
    try {
      await createSegment.mutateAsync({ name: values.name.trim() });
      showSuccess("catalog.messages.segment_created");
      handleClose();
    } catch (err) {
      showError(err);
    }
  };

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={
        <Text fw={600}>
          {t("catalog.segment_form.title", { defaultValue: "Narx segmenti qo'shish" })}
        </Text>
      }
      size="sm"
      centered
    >
      <form onSubmit={form.onSubmit((v) => { void handleSubmit(v); })}>
        <Stack gap="sm">
          <TextInput
            label={t("catalog.segment_form.name_label", { defaultValue: "Segment nomi" })}
            placeholder={t("catalog.segment_form.name_placeholder", { defaultValue: "Masalan: Ulgurji, Chakana" })}
            required
            {...form.getInputProps("name")}
          />
          <Group justify="flex-end" mt="md">
            <Button
              variant="subtle"
              onClick={handleClose}
              disabled={createSegment.isPending}
            >
              {t("common.cancel")}
            </Button>
            <Button type="submit" loading={createSegment.isPending}>
              {t("common.create")}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
