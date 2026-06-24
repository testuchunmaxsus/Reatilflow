/**
 * DeliveryDetailPage — bitta yetkazish tafsiloti.
 *
 * Tarkib:
 * - Holat timeline (assigned → started → delivering → delivered/failed)
 * - Holat o'zgartirish (delivery:edit ruxsati bilan)
 * - Isbot rasm preview modal
 * - Admin uchun yangi kuryer tayinlash modal (delivery:create ruxsati bilan)
 * - GPS trek havolasi
 *
 * i18n: uz/ru, defaultValue bilan.
 */

import {
  Alert,
  Badge,
  Box,
  Button,
  Divider,
  Group,
  Image,
  Loader,
  Modal,
  NumberInput,
  Select,
  Stack,
  Text,
  TextInput,
  ThemeIcon,
  Timeline,
  Title,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import {
  IconAlertCircle,
  IconCheck,
  IconCamera,
  IconMapPin,
  IconTruck,
  IconX,
} from "@tabler/icons-react";
import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Can } from "@/rbac/Can";
import { useApiError } from "@/hooks/useApiError";
import { useCouriers } from "@/features/marketplace/api/marketplaceApi";
import {
  useDelivery,
  useUpdateDeliveryStatus,
  useUploadProofPhoto,
  useAssignCourier,
} from "./api/deliveryApi";
import type { DeliveryStatus } from "./types";
import { DELIVERY_VALID_TRANSITIONS } from "./types";

// ─── Holat badge ─────────────────────────────────────────────────────────────

function DeliveryStatusBadge({ status }: { status: DeliveryStatus | string }) {
  const { t } = useTranslation();
  const colorMap: Record<string, string> = {
    assigned: "blue",
    started: "cyan",
    delivering: "teal",
    delivered: "green",
    failed: "red",
  };
  return (
    <Badge color={colorMap[status] ?? "gray"} variant="filled" size="md">
      {t(`delivery.status.${status}`, { defaultValue: status })}
    </Badge>
  );
}

// ─── Holat Timeline ───────────────────────────────────────────────────────────

const TIMELINE_STEPS: DeliveryStatus[] = [
  "assigned",
  "started",
  "delivering",
  "delivered",
];

function DeliveryTimeline({
  status,
  failedAt,
}: {
  status: DeliveryStatus | string;
  failedAt?: boolean;
}) {
  const { t } = useTranslation();
  const isFailed = status === "failed" || failedAt;

  const activeIdx = TIMELINE_STEPS.indexOf(status as DeliveryStatus);

  return (
    <Timeline active={isFailed ? -1 : activeIdx} bulletSize={24} lineWidth={2}>
      {TIMELINE_STEPS.map((step, idx) => (
        <Timeline.Item
          key={step}
          bullet={
            activeIdx >= idx && !isFailed ? (
              <ThemeIcon size={20} radius="xl" color="teal" variant="filled">
                <IconCheck size={12} />
              </ThemeIcon>
            ) : undefined
          }
          title={t(`delivery.status.${step}`, { defaultValue: step })}
        >
          <Text size="xs" c="dimmed">
            {t(`delivery.timeline.${step}`, { defaultValue: "" })}
          </Text>
        </Timeline.Item>
      ))}
      {isFailed && (
        <Timeline.Item
          bullet={
            <ThemeIcon size={20} radius="xl" color="red" variant="filled">
              <IconX size={12} />
            </ThemeIcon>
          }
          title={t("delivery.status.failed", { defaultValue: "Muvaffaqiyatsiz" })}
          color="red"
        >
          <Text size="xs" c="red">
            {t("delivery.detail.failed_note", { defaultValue: "Yetkazish amalga oshmadi" })}
          </Text>
        </Timeline.Item>
      )}
    </Timeline>
  );
}

// ─── Holat o'zgartirish modal ─────────────────────────────────────────────────

function UpdateStatusModal({
  opened,
  onClose,
  deliveryId,
  currentStatus,
  version,
}: {
  opened: boolean;
  onClose: () => void;
  deliveryId: string;
  currentStatus: DeliveryStatus | string;
  version: number;
}) {
  const { t } = useTranslation();
  const { showError } = useApiError();
  const updateStatus = useUpdateDeliveryStatus();

  const nextStatuses =
    DELIVERY_VALID_TRANSITIONS[currentStatus as DeliveryStatus] ?? [];

  const [newStatus, setNewStatus] = useState<string | null>(
    nextStatuses[0] ?? null,
  );
  const [failureReason, setFailureReason] = useState("");
  const [gpsLat, setGpsLat] = useState<number | string>("");
  const [gpsLng, setGpsLng] = useState<number | string>("");

  const handleClose = () => {
    setNewStatus(nextStatuses[0] ?? null);
    setFailureReason("");
    setGpsLat("");
    setGpsLng("");
    onClose();
  };

  const handleSubmit = async () => {
    if (!newStatus) return;
    try {
      await updateStatus.mutateAsync({
        id: deliveryId,
        data: {
          status: newStatus,
          version,
          gps_lat: gpsLat !== "" ? Number(gpsLat) : null,
          gps_lng: gpsLng !== "" ? Number(gpsLng) : null,
          failure_reason: newStatus === "failed" ? failureReason || null : null,
        },
      });
      notifications.show({
        color: "teal",
        message: t("delivery.messages.status_updated", {
          status: newStatus,
          defaultValue: `Holat '${newStatus}' ga o'zgartirildi`,
        }),
      });
      handleClose();
    } catch (err) {
      showError(err);
    }
  };

  const statusOptions = nextStatuses.map((s) => ({
    value: s,
    label: t(`delivery.status.${s}`, { defaultValue: s }),
  }));

  const isTerminal = nextStatuses.length === 0;

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={
        <Text fw={600}>
          {t("delivery.detail.change_status", { defaultValue: "Holatni o'zgartirish" })}
        </Text>
      }
      size="sm"
      centered
    >
      <Stack gap="md">
        {isTerminal ? (
          <Alert icon={<IconAlertCircle size={16} />} color="gray">
            {t("delivery.detail.terminal_status", {
              defaultValue: "Terminal holat — o'zgartirish mumkin emas",
            })}
          </Alert>
        ) : (
          <>
            <Select
              label={t("delivery.detail.new_status", { defaultValue: "Yangi holat" })}
              data={statusOptions}
              value={newStatus}
              onChange={setNewStatus}
              required
            />
            <Group grow>
              <NumberInput
                label={t("delivery.detail.gps_lat", { defaultValue: "GPS Kenglik" })}
                placeholder="41.2995"
                value={gpsLat}
                onChange={setGpsLat}
                decimalScale={6}
              />
              <NumberInput
                label={t("delivery.detail.gps_lng", { defaultValue: "GPS Uzunlik" })}
                placeholder="69.2401"
                value={gpsLng}
                onChange={setGpsLng}
                decimalScale={6}
              />
            </Group>
            {newStatus === "failed" && (
              <TextInput
                label={t("delivery.detail.failure_reason", {
                  defaultValue: "Muvaffaqiyatsizlik sababi",
                })}
                placeholder={t("delivery.detail.failure_reason_placeholder", {
                  defaultValue: "Sababni kiriting...",
                })}
                value={failureReason}
                onChange={(e) => setFailureReason(e.currentTarget.value)}
              />
            )}
            <Group justify="flex-end">
              <Button
                variant="subtle"
                onClick={handleClose}
                disabled={updateStatus.isPending}
              >
                {t("common.cancel")}
              </Button>
              <Button
                onClick={() => { void handleSubmit(); }}
                disabled={!newStatus}
                loading={updateStatus.isPending}
              >
                {t("common.save")}
              </Button>
            </Group>
          </>
        )}
      </Stack>
    </Modal>
  );
}

// ─── Isbot rasm modal ─────────────────────────────────────────────────────────

function ProofPhotoModal({
  opened,
  onClose,
  photoUrl,
  deliveryId,
}: {
  opened: boolean;
  onClose: () => void;
  photoUrl: string | null;
  deliveryId: string;
}) {
  const { t } = useTranslation();
  const { showError } = useApiError();
  const uploadPhoto = useUploadProofPhoto();
  const [file, setFile] = useState<File | null>(null);

  const handleClose = () => {
    setFile(null);
    onClose();
  };

  const handleUpload = async () => {
    if (!file) return;
    try {
      await uploadPhoto.mutateAsync({ id: deliveryId, file });
      notifications.show({
        color: "teal",
        message: t("delivery.proof.success", { defaultValue: "Isbot rasmi muvaffaqiyatli yuklandi" }),
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
          {t("delivery.proof.title", { defaultValue: "Isbot rasmini yuklash" })}
        </Text>
      }
      size="md"
      centered
    >
      <Stack gap="md">
        {photoUrl && (
          <>
            <Text size="sm" c="dimmed">
              {t("delivery.proof.current_photo", { defaultValue: "Joriy isbot rasmi" })}
            </Text>
            <Image
              src={photoUrl}
              alt="proof"
              mah={260}
              fit="contain"
              radius="sm"
            />
            <Divider />
          </>
        )}

        <Can permission="delivery:edit">
          <Stack gap="xs">
            <Text size="sm">
              {t("delivery.proof.hint", {
                defaultValue: "Yetkazish isboti uchun rasm yuklang (JPEG, PNG, WebP, maks 10 MB)",
              })}
            </Text>
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(e) => setFile(e.currentTarget.files?.[0] ?? null)}
            />
            <Group justify="flex-end">
              <Button
                variant="subtle"
                onClick={handleClose}
                disabled={uploadPhoto.isPending}
              >
                {t("common.close")}
              </Button>
              <Button
                leftSection={<IconCamera size={16} />}
                onClick={() => { void handleUpload(); }}
                disabled={!file}
                loading={uploadPhoto.isPending}
              >
                {t("delivery.proof.upload", { defaultValue: "Yuklash" })}
              </Button>
            </Group>
          </Stack>
        </Can>

        {!photoUrl && (
          <Can permission="delivery:view">
            <Text c="dimmed" ta="center">
              {t("delivery.proof.no_photo", { defaultValue: "Isbot rasmi yuklanmagan" })}
            </Text>
          </Can>
        )}
      </Stack>
    </Modal>
  );
}

// ─── Kuryer tayinlash modal (admin) ───────────────────────────────────────────

function AssignCourierModal({
  opened,
  onClose,
  orderId,
}: {
  opened: boolean;
  onClose: () => void;
  orderId: string;
}) {
  const { t } = useTranslation();
  const { showError } = useApiError();
  const [courierId, setCourierId] = useState<string | null>(null);
  const { data: couriersData } = useCouriers();
  const assignCourier = useAssignCourier();

  const courierOptions =
    couriersData?.items.map((c) => ({
      value: c.id,
      label: c.full_name,
    })) ?? [];

  const handleClose = () => {
    setCourierId(null);
    onClose();
  };

  const handleSubmit = async () => {
    if (!courierId) return;
    try {
      await assignCourier.mutateAsync({ order_id: orderId, courier_id: courierId });
      notifications.show({
        color: "teal",
        message: t("delivery.assign.success", {
          defaultValue: "Kuryer muvaffaqiyatli tayinlandi",
        }),
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
          {t("delivery.assign.title", { defaultValue: "Kuryer tayinlash" })}
        </Text>
      }
      size="sm"
      centered
    >
      <Stack gap="md">
        <Select
          label={t("delivery.assign.courier_label", { defaultValue: "Kuryer" })}
          placeholder={t("delivery.assign.courier_placeholder", {
            defaultValue: "Kuryerni tanlang",
          })}
          data={courierOptions}
          value={courierId}
          onChange={setCourierId}
          searchable
          required
        />
        <Group justify="flex-end">
          <Button
            variant="subtle"
            onClick={handleClose}
            disabled={assignCourier.isPending}
          >
            {t("common.cancel")}
          </Button>
          <Button
            onClick={() => { void handleSubmit(); }}
            disabled={!courierId}
            loading={assignCourier.isPending}
          >
            {t("delivery.assign.submit", { defaultValue: "Tayinlash" })}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

// ─── Asosiy sahifa ────────────────────────────────────────────────────────────

export function DeliveryDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const navigate = useNavigate();

  const { data: delivery, isLoading, isError, error } = useDelivery(id);

  const [statusModalOpened, { open: openStatusModal, close: closeStatusModal }] =
    useDisclosure(false);
  const [proofModalOpened, { open: openProofModal, close: closeProofModal }] =
    useDisclosure(false);
  const [assignModalOpened, { open: openAssignModal, close: closeAssignModal }] =
    useDisclosure(false);

  if (isLoading) {
    return (
      <Group justify="center" py="xl">
        <Loader />
        <Text c="dimmed">{t("common.loading")}</Text>
      </Group>
    );
  }

  if (isError || !delivery) {
    return (
      <Box py="xl" ta="center">
        <Text c="red">
          {error instanceof Error ? error.message : t("errors.unknown")}
        </Text>
        <Button mt="md" variant="subtle" onClick={() => navigate(-1)}>
          {t("delivery.detail.back", { defaultValue: "Orqaga" })}
        </Button>
      </Box>
    );
  }

  return (
    <Stack gap="md">
      {/* Sarlavha */}
      <Group justify="space-between">
        <Group gap="sm">
          <Button variant="subtle" size="xs" onClick={() => navigate(-1)}>
            ← {t("delivery.detail.back", { defaultValue: "Orqaga" })}
          </Button>
          <Title order={3}>
            {t("delivery.detail.title", { defaultValue: "Yetkazish tafsiloti" })}
          </Title>
        </Group>
        <DeliveryStatusBadge status={delivery.status} />
      </Group>

      {/* Asosiy ma'lumot */}
      <Stack gap="xs">
        <Group gap="xs">
          <Text size="sm" fw={500} w={160}>
            {t("delivery.table.order_number", { defaultValue: "Buyurtma" })}:
          </Text>
          <Text size="sm" ff="monospace">
            {delivery.order_id}
          </Text>
        </Group>
        <Group gap="xs">
          <Text size="sm" fw={500} w={160}>
            {t("delivery.table.courier", { defaultValue: "Kuryer" })}:
          </Text>
          <Text size="sm" ff="monospace">
            {delivery.courier_id}
          </Text>
        </Group>
        <Group gap="xs">
          <Text size="sm" fw={500} w={160}>
            {t("delivery.table.assigned_at", { defaultValue: "Tayinlangan" })}:
          </Text>
          <Text size="sm">
            {new Date(delivery.assigned_at).toLocaleString()}
          </Text>
        </Group>
        {delivery.delivered_at && (
          <Group gap="xs">
            <Text size="sm" fw={500} w={160}>
              {t("delivery.table.delivered_at", { defaultValue: "Yetkazilgan" })}:
            </Text>
            <Text size="sm">
              {new Date(delivery.delivered_at).toLocaleString()}
            </Text>
          </Group>
        )}
        {delivery.failure_reason && (
          <Group gap="xs">
            <Text size="sm" fw={500} w={160} c="red">
              {t("delivery.detail.failure_reason", {
                defaultValue: "Muvaffaqiyatsizlik sababi",
              })}:
            </Text>
            <Text size="sm" c="red">
              {delivery.failure_reason}
            </Text>
          </Group>
        )}
        {delivery.gps_track_url && (
          <Group gap="xs">
            <Text size="sm" fw={500} w={160}>
              {t("delivery.route.title", { defaultValue: "Marshrut" })}:
            </Text>
            <Button
              variant="subtle"
              size="xs"
              component="a"
              href={delivery.gps_track_url}
              target="_blank"
              leftSection={<IconMapPin size={14} />}
            >
              {t("delivery.actions.view_route", {
                defaultValue: "Marshrutni ko'rish",
              })}
            </Button>
          </Group>
        )}
      </Stack>

      <Divider />

      {/* Holat timeline */}
      <Box>
        <Text fw={600} mb="sm">
          {t("delivery.detail.timeline", { defaultValue: "Holat tarixi" })}
        </Text>
        <DeliveryTimeline status={delivery.status} failedAt={delivery.status === "failed"} />
      </Box>

      <Divider />

      {/* Amallar */}
      <Group gap="sm">
        {/* Holat o'zgartirish — kuryer/admin */}
        <Can permission="delivery:edit">
          <Button
            leftSection={<IconTruck size={16} />}
            variant="light"
            onClick={openStatusModal}
          >
            {t("delivery.detail.change_status", {
              defaultValue: "Holatni o'zgartirish",
            })}
          </Button>
        </Can>

        {/* Isbot rasm */}
        <Can permission="delivery:edit">
          <Button
            leftSection={<IconCamera size={16} />}
            variant="light"
            color="teal"
            onClick={openProofModal}
          >
            {t("delivery.actions.upload_proof", {
              defaultValue: "Isbot rasmini yuklash",
            })}
          </Button>
        </Can>

        {/* Admin uchun kuryer qayta tayinlash */}
        <Can permission="delivery:create">
          <Button
            leftSection={<IconTruck size={16} />}
            variant="light"
            color="orange"
            onClick={openAssignModal}
          >
            {t("delivery.actions.assign_courier", {
              defaultValue: "Kuryer tayinlash",
            })}
          </Button>
        </Can>

        {/* Faqat ko'rish uchun — isbot rasm preview */}
        {delivery.proof_photo_url && (
          <Button
            leftSection={<IconCamera size={16} />}
            variant="subtle"
            onClick={openProofModal}
          >
            {t("delivery.detail.view_proof", { defaultValue: "Isbot rasmini ko'rish" })}
          </Button>
        )}
      </Group>

      {/* Modallar */}
      <UpdateStatusModal
        opened={statusModalOpened}
        onClose={closeStatusModal}
        deliveryId={delivery.id}
        currentStatus={delivery.status}
        version={delivery.version}
      />

      <ProofPhotoModal
        opened={proofModalOpened}
        onClose={closeProofModal}
        photoUrl={delivery.proof_photo_url}
        deliveryId={delivery.id}
      />

      <Can permission="delivery:create">
        <AssignCourierModal
          opened={assignModalOpened}
          onClose={closeAssignModal}
          orderId={delivery.order_id}
        />
      </Can>
    </Stack>
  );
}
