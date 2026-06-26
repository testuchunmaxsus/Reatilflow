/**
 * PromoBannerUploadModal — aksiya banner rasmini yuklash modal.
 *
 * POST /promos/{id}/banner — multipart/form-data.
 * Ruxsat etilgan formatlar: JPEG, PNG, WebP (max 5MB).
 * RBAC: faqat promo:edit ruxsati.
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
import { useUploadPromoBanner } from "../api/promoApi";
import { useApiError } from "@/hooks/useApiError";
import type { PromoOut } from "../types";

const MAX_SIZE_BYTES = 5 * 1024 * 1024; // 5 MB
const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"];

interface PromoBannerUploadModalProps {
  opened: boolean;
  onClose: () => void;
  promo: PromoOut | null;
}

export function PromoBannerUploadModal({
  opened,
  onClose,
  promo,
}: PromoBannerUploadModalProps) {
  const { t } = useTranslation();
  const { showError, showSuccess } = useApiError();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const uploadBanner = useUploadPromoBanner();

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    setValidationError(null);

    if (!file) return;

    if (!ALLOWED_TYPES.includes(file.type)) {
      setValidationError(
        t("promo.banner.invalid_format", {
          defaultValue: "Faqat JPEG, PNG yoki WebP formatlar ruxsat etiladi",
        }),
      );
      return;
    }
    if (file.size > MAX_SIZE_BYTES) {
      setValidationError(
        t("promo.banner.too_large", { defaultValue: "Fayl 5MB dan katta bo'lmasligi kerak" }),
      );
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
    if (!promo || !selectedFile) return;
    try {
      await uploadBanner.mutateAsync({ id: promo.id, file: selectedFile });
      showSuccess("promo.banner.upload_success");
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
          {t("promo.banner.title", { defaultValue: "Banner yuklash" })}
        </Text>
      }
      size="md"
      centered
    >
      <Stack gap="md">
        {promo?.banner_url && !preview && (
          <Stack gap="xs">
            <Text size="sm" c="dimmed">
              {t("promo.banner.current", { defaultValue: "Hozirgi banner" })}
            </Text>
            <Image src={promo.banner_url} h={160} fit="contain" radius="sm" />
          </Stack>
        )}

        {preview && (
          <Image src={preview} h={200} fit="contain" radius="sm" />
        )}

        {validationError && (
          <Text c="red" size="sm">
            {validationError}
          </Text>
        )}

        <input
          ref={fileInputRef}
          type="file"
          accept=".jpg,.jpeg,.png,.webp"
          onChange={handleFileChange}
          style={{ display: "none" }}
        />

        <Text size="xs" c="dimmed">
          {t("promo.banner.hint", {
            defaultValue: "JPEG, PNG yoki WebP, maksimum 5MB",
          })}
        </Text>

        <Group justify="flex-end">
          <Button
            variant="subtle"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadBanner.isPending}
          >
            {t("promo.banner.choose_file", { defaultValue: "Fayl tanlash" })}
          </Button>
          <Button
            variant="subtle"
            onClick={handleClose}
            disabled={uploadBanner.isPending}
          >
            {t("common.cancel")}
          </Button>
          <Button
            onClick={() => {
              void handleUpload();
            }}
            disabled={!selectedFile}
            loading={uploadBanner.isPending}
          >
            {t("promo.banner.upload", { defaultValue: "Yuklash" })}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
