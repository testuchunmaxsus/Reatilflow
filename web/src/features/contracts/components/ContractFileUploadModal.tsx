/**
 * ContractFileUploadModal — shartnoma faylini yuklash modal.
 *
 * POST /contracts/{id}/file — multipart/form-data.
 * Magic-byte validatsiya backend tomonida: PDF, JPEG, PNG, WebP (max 20 MB).
 * UI da ham asosiy format/hajm tekshiruvi amalga oshiriladi.
 */

import {
  Anchor,
  Button,
  Group,
  Modal,
  Stack,
  Text,
} from "@mantine/core";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useUploadContractFile } from "../api/contractsApi";
import { useApiError } from "@/hooks/useApiError";
import type { ContractOut } from "../types";

// Backend qabul qiladi: PDF, JPEG, PNG, WebP
const MAX_SIZE_BYTES = 20 * 1024 * 1024; // 20 MB
const ALLOWED_TYPES = [
  "application/pdf",
  "image/jpeg",
  "image/png",
  "image/webp",
];

interface ContractFileUploadModalProps {
  opened: boolean;
  onClose: () => void;
  contract: ContractOut | null;
}

export function ContractFileUploadModal({
  opened,
  onClose,
  contract,
}: ContractFileUploadModalProps) {
  const { t } = useTranslation();
  const { showError, showSuccess } = useApiError();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const uploadFile = useUploadContractFile();

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    setValidationError(null);

    if (!file) return;

    if (!ALLOWED_TYPES.includes(file.type)) {
      setValidationError(t("contracts.file.invalid_format"));
      return;
    }
    if (file.size > MAX_SIZE_BYTES) {
      setValidationError(t("contracts.file.too_large"));
      return;
    }

    setSelectedFile(file);
  };

  const handleClose = () => {
    setSelectedFile(null);
    setValidationError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    onClose();
  };

  const handleUpload = async () => {
    if (!contract || !selectedFile) return;
    try {
      await uploadFile.mutateAsync({ id: contract.id, file: selectedFile });
      showSuccess("contracts.file.upload_success");
      handleClose();
    } catch (err) {
      showError(err);
    }
  };

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={<Text fw={600}>{t("contracts.file.title")}</Text>}
      size="md"
      centered
    >
      <Stack gap="md">
        {contract?.file_url && (
          <Stack gap="xs">
            <Text size="sm" c="dimmed">{t("contracts.file.current")}</Text>
            <Anchor
              href={contract.file_url}
              target="_blank"
              rel="noopener noreferrer"
              size="sm"
            >
              {t("contracts.file.view_current")}
            </Anchor>
          </Stack>
        )}

        {selectedFile && (
          <Text size="sm" c="teal">
            {t("contracts.file.selected")}: {selectedFile.name}
          </Text>
        )}

        {validationError && (
          <Text c="red" size="sm">{validationError}</Text>
        )}

        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.jpg,.jpeg,.png,.webp"
          onChange={handleFileChange}
          style={{ display: "none" }}
        />

        <Text size="xs" c="dimmed">
          {t("contracts.file.hint")}
        </Text>

        <Group justify="flex-end">
          <Button
            variant="subtle"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadFile.isPending}
          >
            {t("contracts.file.choose_file")}
          </Button>
          <Button
            variant="subtle"
            onClick={handleClose}
            disabled={uploadFile.isPending}
          >
            {t("common.cancel")}
          </Button>
          <Button
            onClick={() => { void handleUpload(); }}
            disabled={!selectedFile}
            loading={uploadFile.isPending}
          >
            {t("contracts.file.upload")}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
