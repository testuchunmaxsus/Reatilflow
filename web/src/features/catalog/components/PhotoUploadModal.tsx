/**
 * PhotoUploadModal — mahsulot rasmini yuklash modal.
 *
 * POST /catalog/products/{id}/photo — multipart/form-data.
 * Ruxsat etilgan formatlar: JPEG, PNG, WebP (max 5MB).
 */

import {
  Button,
  Group,
  Image,
  Modal,
  Stack,
  Text,
} from "@mantine/core";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useUploadPhoto } from "../api/catalogApi";
import { useApiError } from "@/hooks/useApiError";
import type { ProductOut } from "@/api/types";

const MAX_SIZE_BYTES = 5 * 1024 * 1024; // 5 MB
const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"];

interface PhotoUploadModalProps {
  opened: boolean;
  onClose: () => void;
  product: ProductOut | null;
}

export function PhotoUploadModal({
  opened,
  onClose,
  product,
}: PhotoUploadModalProps) {
  const { t } = useTranslation();
  const { showError, showSuccess } = useApiError();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const uploadPhoto = useUploadPhoto();

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    setValidationError(null);

    if (!file) return;

    if (!ALLOWED_TYPES.includes(file.type)) {
      setValidationError(t("catalog.photo.invalid_format"));
      return;
    }
    if (file.size > MAX_SIZE_BYTES) {
      setValidationError(t("catalog.photo.too_large"));
      return;
    }

    setSelectedFile(file);
    const url = URL.createObjectURL(file);
    setPreview(url);
  };

  const handleClose = () => {
    setPreview(null);
    setSelectedFile(null);
    setValidationError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    onClose();
  };

  const handleUpload = async () => {
    if (!product || !selectedFile) return;
    try {
      await uploadPhoto.mutateAsync({ id: product.id, file: selectedFile });
      showSuccess("catalog.photo.upload_success");
      handleClose();
    } catch (err) {
      showError(err);
    }
  };

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={<Text fw={600}>{t("catalog.photo.title")}</Text>}
      size="md"
      centered
    >
      <Stack gap="md">
        {product?.photo_url && !preview && (
          <Stack gap="xs">
            <Text size="sm" c="dimmed">{t("catalog.photo.current")}</Text>
            <Image src={product.photo_url} h={160} fit="contain" radius="sm" />
          </Stack>
        )}

        {preview && (
          <Image src={preview} h={200} fit="contain" radius="sm" />
        )}

        {validationError && (
          <Text c="red" size="sm">{validationError}</Text>
        )}

        <input
          ref={fileInputRef}
          type="file"
          accept=".jpg,.jpeg,.png,.webp"
          onChange={handleFileChange}
          style={{ display: "none" }}
        />

        <Text size="xs" c="dimmed">
          {t("catalog.photo.hint")}
        </Text>

        <Group justify="flex-end">
          <Button
            variant="subtle"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadPhoto.isPending}
          >
            {t("catalog.photo.choose_file")}
          </Button>
          <Button
            variant="subtle"
            onClick={handleClose}
            disabled={uploadPhoto.isPending}
          >
            {t("common.cancel")}
          </Button>
          <Button
            onClick={() => { void handleUpload(); }}
            disabled={!selectedFile}
            loading={uploadPhoto.isPending}
          >
            {t("catalog.photo.upload")}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
