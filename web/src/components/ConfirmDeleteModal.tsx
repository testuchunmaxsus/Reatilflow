/**
 * ConfirmDeleteModal — umumiy o'chirish tasdiqlash modal.
 *
 * @mantine/modals o'rnatilmagan, shuning uchun oddiy Modal ishlatiladi.
 */

import { Button, Group, Modal, Text } from "@mantine/core";
import { useTranslation } from "react-i18next";

interface ConfirmDeleteModalProps {
  opened: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  message: string;
  loading?: boolean;
}

export function ConfirmDeleteModal({
  opened,
  onClose,
  onConfirm,
  title,
  message,
  loading = false,
}: ConfirmDeleteModalProps) {
  const { t } = useTranslation();

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={<Text fw={600}>{title}</Text>}
      size="sm"
      centered
    >
      <Text size="sm" mb="md">
        {message}
      </Text>
      <Group justify="flex-end">
        <Button variant="subtle" onClick={onClose} disabled={loading}>
          {t("common.cancel")}
        </Button>
        <Button color="red" onClick={onConfirm} loading={loading}>
          {t("common.delete")}
        </Button>
      </Group>
    </Modal>
  );
}
