/**
 * CourierDashboardPage — kuryer uchun bosh sahifa.
 *
 * Tarkib:
 * - Faol yetkazishlar (status: delivering) — kartalar
 * - Metrikalar: jami tayinlangan, yetkazilgan, muvaffaqiyatsiz
 * - Marketplace kuryer yetkazishlari (GET /marketplace/orders/deliveries)
 * - Har bir yetkazish uchun holat o'zgartirish va isbot rasm yuklash
 *
 * Mobil CourierDashboard ekvivalenti (veb).
 * i18n: uz/ru, defaultValue bilan.
 */

import {
  Badge,
  Box,
  Button,
  Card,
  Divider,
  Group,
  Loader,
  Modal,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import {
  IconCamera,
  IconCheck,
  IconPackage,
  IconTruck,
  IconX,
} from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useApiError } from "@/hooks/useApiError";
import type { IncomingOrder } from "@/features/marketplace/types";
import {
  useDeliveries,
  useUpdateDeliveryStatus,
  useUploadProofPhoto,
  useMarketplaceCourierDeliveries,
  useMarketplaceUploadProofPhoto,
} from "./api/deliveryApi";
import type { Delivery } from "./types";

const PAGE_SIZE = 10;

// ─── Metrika kartasi ──────────────────────────────────────────────────────────

function MetricCard({
  label,
  value,
  color,
  icon: Icon,
}: {
  label: string;
  value: number;
  color: string;
  icon: React.ComponentType<{ size?: number | string; color?: string }>;
}) {
  return (
    <Card shadow="xs" radius="sm" p="md" withBorder>
      <Group gap="sm">
        <Icon size={28} color={`var(--mantine-color-${color}-6)`} />
        <Box>
          <Text size="xl" fw={700} c={color}>
            {value}
          </Text>
          <Text size="xs" c="dimmed">
            {label}
          </Text>
        </Box>
      </Group>
    </Card>
  );
}

// ─── Delivery yetkazish kartasi ───────────────────────────────────────────────

function DeliveryCard({
  delivery,
  onStatusUpdate,
  onProofUpload,
}: {
  delivery: Delivery;
  onStatusUpdate: (delivery: Delivery) => void;
  onProofUpload: (delivery: Delivery) => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const colorMap: Record<string, string> = {
    assigned: "blue",
    started: "cyan",
    delivering: "teal",
    delivered: "green",
    failed: "red",
  };

  return (
    <Card shadow="xs" radius="sm" p="md" withBorder>
      <Stack gap="xs">
        <Group justify="space-between">
          <Text size="sm" fw={500} ff="monospace">
            #{delivery.order_id.slice(0, 8)}…
          </Text>
          <Badge
            color={colorMap[delivery.status] ?? "gray"}
            variant="light"
            size="sm"
          >
            {t(`delivery.status.${delivery.status}`, {
              defaultValue: delivery.status,
            })}
          </Badge>
        </Group>

        <Text size="xs" c="dimmed">
          {t("delivery.table.assigned_at", { defaultValue: "Tayinlangan" })}:{" "}
          {new Date(delivery.assigned_at).toLocaleDateString()}
        </Text>

        <Group gap="xs" mt="xs">
          {delivery.status !== "delivered" && delivery.status !== "failed" && (
            <Button
              size="xs"
              variant="light"
              leftSection={<IconTruck size={14} />}
              onClick={() => onStatusUpdate(delivery)}
            >
              {t("delivery.detail.change_status", {
                defaultValue: "Holat",
              })}
            </Button>
          )}
          {delivery.status === "delivering" && (
            <Button
              size="xs"
              variant="light"
              color="teal"
              leftSection={<IconCamera size={14} />}
              onClick={() => onProofUpload(delivery)}
            >
              {t("delivery.actions.upload_proof", { defaultValue: "Isbot" })}
            </Button>
          )}
          <Button
            size="xs"
            variant="subtle"
            onClick={() => navigate(`/delivery/${delivery.id}`)}
          >
            {t("common.edit", { defaultValue: "Ko'rish" })}
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}

// ─── Marketplace yetkazish kartasi ────────────────────────────────────────────

function MarketplaceDeliveryCard({
  order,
  onProofUpload,
}: {
  order: IncomingOrder;
  onProofUpload: (order: IncomingOrder) => void;
}) {
  const { t } = useTranslation();

  return (
    <Card shadow="xs" radius="sm" p="md" withBorder style={{ borderLeft: "3px solid var(--mantine-color-violet-5)" }}>
      <Stack gap="xs">
        <Group justify="space-between">
          <Group gap="xs">
            <IconPackage size={16} color="var(--mantine-color-violet-6)" />
            <Text size="sm" fw={500}>
              {order.buyer_store_name ?? "—"}
            </Text>
          </Group>
          <Badge color="violet" variant="light" size="sm">
            Marketplace
          </Badge>
        </Group>

        <Text size="xs" c="dimmed">
          {order.lines.length}{" "}
          {t("marketplace.table.items_count", { defaultValue: "ta" })}{" "}
          · {order.total_amount.toLocaleString()} UZS
        </Text>

        <Group gap="xs" mt="xs">
          <Button
            size="xs"
            variant="light"
            color="teal"
            leftSection={<IconCamera size={14} />}
            onClick={() => onProofUpload(order)}
          >
            {t("delivery.actions.upload_proof", {
              defaultValue: "Isbot rasmini yuklash",
            })}
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}

// ─── Holat o'zgartirish modal (kuryer uchun soddalashtirilgan) ────────────────

function QuickStatusModal({
  opened,
  onClose,
  delivery,
}: {
  opened: boolean;
  onClose: () => void;
  delivery: Delivery | null;
}) {
  const { t } = useTranslation();
  const { showError } = useApiError();
  const updateStatus = useUpdateDeliveryStatus();

  if (!delivery) return null;

  const nextMap: Record<string, { status: string; label: string; color: string; icon: React.ReactNode }[]> = {
    assigned: [
      { status: "started", label: t("delivery.status.started", { defaultValue: "Yo'lga chiqdim" }), color: "cyan", icon: <IconTruck size={16} /> },
    ],
    started: [
      { status: "delivering", label: t("delivery.status.delivering", { defaultValue: "Yetkazilmoqda" }), color: "teal", icon: <IconTruck size={16} /> },
    ],
    delivering: [
      { status: "delivered", label: t("delivery.status.delivered", { defaultValue: "Yetkazildi" }), color: "green", icon: <IconCheck size={16} /> },
      { status: "failed", label: t("delivery.status.failed", { defaultValue: "Muvaffaqiyatsiz" }), color: "red", icon: <IconX size={16} /> },
    ],
  };

  const actions = nextMap[delivery.status] ?? [];

  const handleAction = async (newStatus: string) => {
    try {
      await updateStatus.mutateAsync({
        id: delivery.id,
        data: { status: newStatus, version: delivery.version },
      });
      notifications.show({
        color: "teal",
        message: t("delivery.messages.status_updated", {
          status: newStatus,
          defaultValue: `Holat '${newStatus}' ga o'zgartirildi`,
        }),
      });
      onClose();
    } catch (err) {
      showError(err);
    }
  };

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={
        <Text fw={600}>
          {t("delivery.detail.change_status", { defaultValue: "Holatni o'zgartirish" })}
        </Text>
      }
      size="sm"
      centered
    >
      <Stack gap="sm">
        {actions.length === 0 ? (
          <Text c="dimmed" ta="center">
            {t("delivery.detail.terminal_status", {
              defaultValue: "Terminal holat — o'zgartirish mumkin emas",
            })}
          </Text>
        ) : (
          actions.map((action) => (
            <Button
              key={action.status}
              color={action.color}
              leftSection={action.icon}
              fullWidth
              loading={updateStatus.isPending}
              onClick={() => { void handleAction(action.status); }}
            >
              {action.label}
            </Button>
          ))
        )}
        <Button variant="subtle" onClick={onClose} disabled={updateStatus.isPending}>
          {t("common.cancel")}
        </Button>
      </Stack>
    </Modal>
  );
}

// ─── Isbot rasm yuklash modal ─────────────────────────────────────────────────

function ProofUploadModal({
  opened,
  onClose,
  deliveryId,
  isMarketplace,
}: {
  opened: boolean;
  onClose: () => void;
  deliveryId: string;
  isMarketplace: boolean;
}) {
  const { t } = useTranslation();
  const { showError } = useApiError();
  const uploadDelivery = useUploadProofPhoto();
  const uploadMarketplace = useMarketplaceUploadProofPhoto();
  const [file, setFile] = useState<File | null>(null);

  const isPending = uploadDelivery.isPending || uploadMarketplace.isPending;

  const handleClose = () => {
    setFile(null);
    onClose();
  };

  const handleUpload = async () => {
    if (!file) return;
    try {
      if (isMarketplace) {
        await uploadMarketplace.mutateAsync({ orderId: deliveryId, file });
      } else {
        await uploadDelivery.mutateAsync({ id: deliveryId, file });
      }
      notifications.show({
        color: "teal",
        message: t("delivery.proof.success", {
          defaultValue: "Isbot rasmi muvaffaqiyatli yuklandi",
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
          {t("delivery.proof.title", { defaultValue: "Isbot rasmini yuklash" })}
        </Text>
      }
      size="sm"
      centered
    >
      <Stack gap="md">
        <Text size="sm" c="dimmed">
          {t("delivery.proof.hint", {
            defaultValue:
              "Yetkazish isboti uchun rasm yuklang (JPEG, PNG, WebP, maks 10 MB)",
          })}
        </Text>
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          onChange={(e) => setFile(e.currentTarget.files?.[0] ?? null)}
        />
        <Group justify="flex-end">
          <Button variant="subtle" onClick={handleClose} disabled={isPending}>
            {t("common.cancel")}
          </Button>
          <Button
            leftSection={<IconCamera size={16} />}
            onClick={() => { void handleUpload(); }}
            disabled={!file}
            loading={isPending}
          >
            {t("delivery.proof.upload", { defaultValue: "Yuklash" })}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

// ─── Asosiy sahifa ────────────────────────────────────────────────────────────

export function CourierDashboardPage() {
  const { t } = useTranslation();

  // Barcha yetkazishlar (metrika uchun)
  const { data: allData, isLoading: allLoading } = useDeliveries({ limit: 100, offset: 0 });

  // Faol yetkazishlar
  const { data: activeData, isLoading: activeLoading } = useDeliveries({
    status: "delivering",
    limit: PAGE_SIZE,
    offset: 0,
  });

  // Marketplace kuryer yetkazishlari
  const { data: mpData, isLoading: mpLoading } = useMarketplaceCourierDeliveries({
    limit: PAGE_SIZE,
    offset: 0,
  });

  // Holat modal
  const [statusModalOpened, { open: openStatusModal, close: closeStatusModal }] =
    useDisclosure(false);
  const [selectedDelivery, setSelectedDelivery] = useState<Delivery | null>(null);

  // Isbot rasm modal
  const [proofModalOpened, { open: openProofModal, close: closeProofModal }] =
    useDisclosure(false);
  const [proofTarget, setProofTarget] = useState<{
    id: string;
    isMarketplace: boolean;
  } | null>(null);

  const handleStatusUpdate = (delivery: Delivery) => {
    setSelectedDelivery(delivery);
    openStatusModal();
  };

  const handleProofUpload = (delivery: Delivery) => {
    setProofTarget({ id: delivery.id, isMarketplace: false });
    openProofModal();
  };

  const handleMpProofUpload = (order: IncomingOrder) => {
    setProofTarget({ id: order.id, isMarketplace: true });
    openProofModal();
  };

  // Metrikalar
  const totalAssigned = allData?.total ?? 0;
  const totalDelivered = allData?.items.filter((d) => d.status === "delivered").length ?? 0;
  const totalFailed = allData?.items.filter((d) => d.status === "failed").length ?? 0;

  return (
    <Stack gap="md">
      <Title order={3}>
        {t("delivery.courier_dashboard.title", { defaultValue: "Kuryer paneli" })}
      </Title>

      {/* Metrikalar */}
      {allLoading ? (
        <Group justify="center" py="md">
          <Loader size="sm" />
        </Group>
      ) : (
        <SimpleGrid cols={{ base: 1, xs: 3 }} spacing="sm">
          <MetricCard
            label={t("delivery.courier_dashboard.total_assigned", {
              defaultValue: "Jami tayinlangan",
            })}
            value={totalAssigned}
            color="blue"
            icon={IconTruck}
          />
          <MetricCard
            label={t("delivery.courier_dashboard.total_delivered", {
              defaultValue: "Yetkazildi",
            })}
            value={totalDelivered}
            color="green"
            icon={IconCheck}
          />
          <MetricCard
            label={t("delivery.courier_dashboard.total_failed", {
              defaultValue: "Muvaffaqiyatsiz",
            })}
            value={totalFailed}
            color="red"
            icon={IconX}
          />
        </SimpleGrid>
      )}

      <Divider />

      {/* Faol yetkazishlar */}
      <Box>
        <Text fw={600} mb="sm">
          {t("delivery.courier_dashboard.active_deliveries", {
            defaultValue: "Faol yetkazishlar",
          })}
        </Text>
        {activeLoading ? (
          <Group justify="center" py="md">
            <Loader size="sm" />
          </Group>
        ) : !activeData?.items.length ? (
          <Text c="dimmed" ta="center" py="md">
            {t("delivery.courier_dashboard.no_active", {
              defaultValue: "Faol yetkazishlar yo'q",
            })}
          </Text>
        ) : (
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
            {activeData.items.map((delivery) => (
              <DeliveryCard
                key={delivery.id}
                delivery={delivery}
                onStatusUpdate={handleStatusUpdate}
                onProofUpload={handleProofUpload}
              />
            ))}
          </SimpleGrid>
        )}
      </Box>

      <Divider />

      {/* Marketplace yetkazishlar */}
      <Box>
        <Text fw={600} mb="sm">
          {t("delivery.courier_dashboard.marketplace_deliveries", {
            defaultValue: "Marketplace yetkazishlar",
          })}
        </Text>
        {mpLoading ? (
          <Group justify="center" py="md">
            <Loader size="sm" />
          </Group>
        ) : !mpData?.items.length ? (
          <Text c="dimmed" ta="center" py="md">
            {t("delivery.courier_dashboard.no_marketplace", {
              defaultValue: "Marketplace yetkazishlar yo'q",
            })}
          </Text>
        ) : (
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
            {mpData.items.map((order) => (
              <MarketplaceDeliveryCard
                key={order.id}
                order={order}
                onProofUpload={handleMpProofUpload}
              />
            ))}
          </SimpleGrid>
        )}
      </Box>

      {/* Modallar */}
      <QuickStatusModal
        opened={statusModalOpened}
        onClose={() => {
          setSelectedDelivery(null);
          closeStatusModal();
        }}
        delivery={selectedDelivery}
      />

      {proofTarget && (
        <ProofUploadModal
          opened={proofModalOpened}
          onClose={() => {
            setProofTarget(null);
            closeProofModal();
          }}
          deliveryId={proofTarget.id}
          isMarketplace={proofTarget.isMarketplace}
        />
      )}
    </Stack>
  );
}
