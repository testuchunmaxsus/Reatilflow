/**
 * BannerFormModal — banner yaratish / tahrirlash modal.
 *
 * POST /marketplace/banners  — yaratish
 * PATCH /marketplace/banners/{id} — tahrirlash
 * POST /marketplace/banners/{id}/image — rasm yuklash (tahrirlashda)
 *
 * Backend AdBannerOut kontrakti:
 *   title (bitta, uz/ru emas), priority (int), valid_from (date, MAJBURIY),
 *   valid_to (date, MAJBURIY), target_url, target_product_id, is_active
 */

import {
  Button,
  Checkbox,
  Group,
  Image,
  Modal,
  NumberInput,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { notifications } from "@mantine/notifications";
import {
  useCreateBanner,
  useUpdateBanner,
  useUploadBannerImage,
} from "../api/marketplaceApi";
import { useApiError } from "@/hooks/useApiError";
import { toLocalYMD, parseYMD } from "@/utils/date";
import type { BannerOut } from "../types";

const MAX_IMAGE_SIZE = 5 * 1024 * 1024; // 5 MB
const ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];

interface BannerFormModalProps {
  opened: boolean;
  onClose: () => void;
  banner?: BannerOut;
}

export function BannerFormModal({
  opened,
  onClose,
  banner,
}: BannerFormModalProps) {
  const { t } = useTranslation();
  const { showError } = useApiError();
  const isEdit = Boolean(banner);

  const [title, setTitle] = useState(banner?.title ?? "");
  const [targetUrl, setTargetUrl] = useState(banner?.target_url ?? "");
  const [isActive, setIsActive] = useState(banner?.is_active ?? true);
  const [priority, setPriority] = useState<number | string>(
    banner?.priority ?? 0,
  );
  const [validFrom, setValidFrom] = useState<Date | null>(
    parseYMD(banner?.valid_from ?? null),
  );
  const [validTo, setValidTo] = useState<Date | null>(
    parseYMD(banner?.valid_to ?? null),
  );

  // Rasm yuklash
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);

  // Validatsiya xatolari
  const [errors, setErrors] = useState<Record<string, string>>({});

  const createBanner = useCreateBanner();
  const updateBanner = useUpdateBanner();
  const uploadImage = useUploadBannerImage();

  const isPending =
    createBanner.isPending || updateBanner.isPending || uploadImage.isPending;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    setImageError(null);
    if (!file) return;
    if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
      setImageError(t("catalog.photo.invalid_format"));
      return;
    }
    if (file.size > MAX_IMAGE_SIZE) {
      setImageError(t("catalog.photo.too_large"));
      return;
    }
    setSelectedFile(file);
  };

  const validate = (): boolean => {
    const errs: Record<string, string> = {};
    if (!title.trim()) errs.title = t("marketplace.banner.form.title_required");
    if (!validFrom) errs.valid_from = t("marketplace.banner.form.valid_from_required");
    if (!validTo) errs.valid_to = t("marketplace.banner.form.valid_to_required");
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleClose = () => {
    setTitle(banner?.title ?? "");
    setTargetUrl(banner?.target_url ?? "");
    setIsActive(banner?.is_active ?? true);
    setPriority(banner?.priority ?? 0);
    setValidFrom(parseYMD(banner?.valid_from ?? null));
    setValidTo(parseYMD(banner?.valid_to ?? null));
    setSelectedFile(null);
    setImageError(null);
    setErrors({});
    if (fileInputRef.current) fileInputRef.current.value = "";
    onClose();
  };

  const handleSubmit = async () => {
    if (!validate()) return;

    const payload = {
      title: title.trim(),
      target_url: targetUrl.trim() || null,
      is_active: isActive,
      priority: typeof priority === "number" ? priority : 0,
      valid_from: toLocalYMD(validFrom!),
      valid_to: toLocalYMD(validTo!),
    };

    try {
      let savedBanner: BannerOut;

      if (isEdit && banner) {
        savedBanner = await updateBanner.mutateAsync({
          id: banner.id,
          data: payload,
        });
      } else {
        savedBanner = await createBanner.mutateAsync(payload);
      }

      // Rasm yuklash (agar tanlangan bo'lsa)
      if (selectedFile) {
        await uploadImage.mutateAsync({
          id: savedBanner.id,
          file: selectedFile,
        });
      }

      notifications.show({
        color: "green",
        message: isEdit
          ? t("marketplace.banner.messages.updated")
          : t("marketplace.banner.messages.created"),
      });
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
          {isEdit
            ? t("marketplace.banner.form.edit_title")
            : t("marketplace.banner.form.create_title")}
        </Text>
      }
      size="md"
      centered
    >
      <Stack gap="sm">
        <TextInput
          label={t("marketplace.banner.form.title")}
          placeholder={t("marketplace.banner.form.title_placeholder")}
          value={title}
          onChange={(e) => setTitle(e.currentTarget.value)}
          error={errors.title}
          required
        />

        <DateInput
          label={t("marketplace.banner.form.valid_from")}
          placeholder="2026-01-01"
          value={validFrom}
          onChange={setValidFrom}
          error={errors.valid_from}
          required
          valueFormat="YYYY-MM-DD"
          clearable
        />

        <DateInput
          label={t("marketplace.banner.form.valid_to")}
          placeholder="2026-12-31"
          value={validTo}
          onChange={setValidTo}
          error={errors.valid_to}
          required
          valueFormat="YYYY-MM-DD"
          clearable
        />

        <NumberInput
          label={t("marketplace.banner.form.priority")}
          value={priority}
          onChange={setPriority}
          min={0}
          step={1}
        />

        <TextInput
          label={t("marketplace.banner.form.target_url")}
          placeholder="https://..."
          value={targetUrl}
          onChange={(e) => setTargetUrl(e.currentTarget.value)}
        />

        <Checkbox
          label={t("marketplace.banner.form.is_active")}
          checked={isActive}
          onChange={(e) => setIsActive(e.currentTarget.checked)}
        />

        {/* Rasm */}
        <Stack gap="xs">
          <Text size="sm" fw={500}>
            {t("marketplace.banner.form.image")}
          </Text>

          {banner?.image_url && !selectedFile && (
            <Image
              src={banner.image_url}
              h={80}
              fit="contain"
              radius="sm"
              alt="banner"
            />
          )}

          {selectedFile && (
            <Text size="sm" c="teal">
              {selectedFile.name}
            </Text>
          )}

          {imageError && (
            <Text size="sm" c="red">
              {imageError}
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
            {t("marketplace.banner.form.image_hint")}
          </Text>

          <Button
            variant="subtle"
            size="xs"
            onClick={() => fileInputRef.current?.click()}
            disabled={isPending}
          >
            {t("marketplace.banner.form.choose_image")}
          </Button>
        </Stack>

        <Group justify="flex-end" mt="xs">
          <Button variant="subtle" onClick={handleClose} disabled={isPending}>
            {t("common.cancel")}
          </Button>
          <Button
            onClick={() => { void handleSubmit(); }}
            loading={isPending}
          >
            {isEdit ? t("common.save") : t("common.create")}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
