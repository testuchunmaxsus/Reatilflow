/**
 * SuperadminBannersPage — banner moderatsiya sahifasi.
 *
 * Xususiyatlar:
 * - Jadval: rasm (Image), title, korxona (enterprise_name), status badge,
 *   priority, valid_from/to
 * - is_active toggle (PATCH /marketplace/banners/{id})
 * - O'chirish (DELETE /marketplace/banners/{id}) + ConfirmDeleteModal
 * - Filtr: korxona + holat
 * - Pagination
 */

import {
  Badge,
  Box,
  Group,
  Image,
  Loader,
  Pagination,
  Select,
  Stack,
  Switch,
  Table,
  Text,
  Title,
  ActionIcon,
  Tooltip,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { IconTrash } from "@tabler/icons-react";
import { useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { notifications } from "@mantine/notifications";
import {
  useSuperadminBanners,
  useToggleBannerActive,
  useDeleteBanner,
  useEnterprises,
} from "./api/superadminApi";
import { ConfirmDeleteModal } from "@/components/ConfirmDeleteModal";
import { useApiError } from "@/hooks/useApiError";
import type { SuperadminBannerOut } from "./types";
import { formatDate } from "@/utils/date";

const PAGE_SIZE = 20;

// ─── Status badge ─────────────────────────────────────────────────────────────

function BannerStatusBadge({ is_active }: { is_active: boolean }) {
  const { t } = useTranslation();
  return (
    <Badge
      color={is_active ? "green" : "gray"}
      variant="dot"
      size="sm"
    >
      {is_active
        ? t("superadmin.banners.status.active")
        : t("superadmin.banners.status.inactive")}
    </Badge>
  );
}

// ─── Komponent ────────────────────────────────────────────────────────────────

export function SuperadminBannersPage() {
  const { t } = useTranslation();
  const { showError } = useApiError();

  const [page, setPage] = useState(1);
  const [enterpriseFilter, setEnterpriseFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<"" | "true" | "false">("");

  const [deleteOpened, { open: openDelete, close: closeDelete }] =
    useDisclosure(false);
  const [deletingBanner, setDeletingBanner] =
    useState<SuperadminBannerOut | null>(null);

  const offset = (page - 1) * PAGE_SIZE;

  const isActiveParam =
    statusFilter === "true"
      ? true
      : statusFilter === "false"
        ? false
        : null;

  const { data, isLoading, isError, error } = useSuperadminBanners({
    enterprise_id: enterpriseFilter,
    is_active: isActiveParam,
    limit: PAGE_SIZE,
    offset,
  });

  const { data: enterprisesData } = useEnterprises({ limit: 100, offset: 0 });
  const toggleMutation = useToggleBannerActive();
  const deleteMutation = useDeleteBanner();

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1;

  const handleEnterpriseChange = useCallback((val: string | null) => {
    setEnterpriseFilter(val ?? "");
    setPage(1);
  }, []);

  const handleStatusChange = useCallback((val: string | null) => {
    setStatusFilter((val ?? "") as "" | "true" | "false");
    setPage(1);
  }, []);

  const handleToggle = async (banner: SuperadminBannerOut) => {
    try {
      await toggleMutation.mutateAsync({
        id: banner.id,
        is_active: !banner.is_active,
      });
      notifications.show({
        color: banner.is_active ? "gray" : "green",
        message: banner.is_active
          ? t("superadmin.banners.messages.deactivated", {
              name: banner.title,
            })
          : t("superadmin.banners.messages.activated", {
              name: banner.title,
            }),
      });
    } catch (err) {
      showError(err);
    }
  };

  const handleDeleteClick = (banner: SuperadminBannerOut) => {
    setDeletingBanner(banner);
    openDelete();
  };

  const handleConfirmDelete = async () => {
    if (!deletingBanner) return;
    try {
      await deleteMutation.mutateAsync(deletingBanner.id);
      notifications.show({
        color: "red",
        message: t("superadmin.banners.messages.deleted", {
          name: deletingBanner.title,
        }),
      });
      closeDelete();
    } catch (err) {
      showError(err);
    }
  };

  const enterpriseOptions = (enterprisesData?.items ?? []).map((ent) => ({
    value: ent.id,
    label: ent.name,
  }));

  return (
    <Stack gap="md">
      {/* Sarlavha */}
      <Title order={3}>{t("superadmin.banners.title")}</Title>

      {/* Filtrlar */}
      <Group gap="sm" wrap="wrap">
        <Select
          placeholder={t("superadmin.banners.filter.all_enterprises")}
          value={enterpriseFilter || null}
          onChange={handleEnterpriseChange}
          data={enterpriseOptions}
          clearable
          searchable
          w={240}
          aria-label={t("superadmin.banners.filter.enterprise")}
        />
        <Select
          placeholder={t("superadmin.banners.filter.all_statuses")}
          value={statusFilter || null}
          onChange={handleStatusChange}
          data={[
            { value: "true", label: t("superadmin.banners.status.active") },
            { value: "false", label: t("superadmin.banners.status.inactive") },
          ]}
          clearable
          w={180}
          aria-label={t("superadmin.banners.filter.status")}
        />
      </Group>

      {/* Jadval */}
      {isLoading ? (
        <Group justify="center" py="xl">
          <Loader />
          <Text c="dimmed">{t("common.loading")}</Text>
        </Group>
      ) : isError ? (
        <Box py="xl" ta="center">
          <Text c="red">
            {error instanceof Error ? error.message : t("errors.unknown")}
          </Text>
        </Box>
      ) : !data?.items.length ? (
        <Box py="xl" ta="center">
          <Text c="dimmed">{t("superadmin.banners.empty")}</Text>
        </Box>
      ) : (
        <Table.ScrollContainer minWidth={900}>
          <Table striped highlightOnHover withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t("superadmin.banners.table.image")}</Table.Th>
                <Table.Th>{t("superadmin.banners.table.title")}</Table.Th>
                <Table.Th>{t("superadmin.banners.table.enterprise")}</Table.Th>
                <Table.Th>{t("superadmin.banners.table.status")}</Table.Th>
                <Table.Th>{t("superadmin.banners.table.priority")}</Table.Th>
                <Table.Th>{t("superadmin.banners.table.valid_from")}</Table.Th>
                <Table.Th>{t("superadmin.banners.table.valid_to")}</Table.Th>
                <Table.Th>{t("catalog.table.actions")}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.items.map((banner) => (
                <Table.Tr key={banner.id}>
                  <Table.Td>
                    {banner.image_url ? (
                      <Image
                        src={banner.image_url}
                        h={40}
                        w={60}
                        fit="cover"
                        radius="sm"
                        alt={banner.title}
                      />
                    ) : (
                      <Box
                        h={40}
                        w={60}
                        bg="gray.2"
                        style={{ borderRadius: 4 }}
                      />
                    )}
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" fw={500}>
                      {banner.title}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed">
                      {banner.enterprise_name}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <BannerStatusBadge is_active={banner.is_active} />
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{banner.priority}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed">
                      {banner.valid_from ? formatDate(banner.valid_from) : "—"}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed">
                      {banner.valid_to ? formatDate(banner.valid_to) : "—"}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Group gap={8}>
                      <Tooltip
                        label={
                          banner.is_active
                            ? t("superadmin.banners.actions.deactivate")
                            : t("superadmin.banners.actions.activate")
                        }
                      >
                        <Switch
                          checked={banner.is_active}
                          onChange={() => { void handleToggle(banner); }}
                          disabled={toggleMutation.isPending}
                          size="xs"
                          aria-label={
                            banner.is_active
                              ? t("superadmin.banners.actions.deactivate")
                              : t("superadmin.banners.actions.activate")
                          }
                        />
                      </Tooltip>
                      <Tooltip label={t("common.delete")}>
                        <ActionIcon
                          variant="subtle"
                          color="red"
                          onClick={() => handleDeleteClick(banner)}
                          aria-label={t("common.delete")}
                        >
                          <IconTrash size={16} />
                        </ActionIcon>
                      </Tooltip>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <Group justify="center">
          <Pagination
            value={page}
            onChange={setPage}
            total={totalPages}
            size="sm"
          />
        </Group>
      )}

      {/* O'chirish tasdiqlash modali */}
      <ConfirmDeleteModal
        opened={deleteOpened}
        onClose={closeDelete}
        onConfirm={() => { void handleConfirmDelete(); }}
        title={t("superadmin.banners.delete.title")}
        message={
          deletingBanner
            ? t("superadmin.banners.delete.confirm", {
                name: deletingBanner.title,
              })
            : ""
        }
        loading={deleteMutation.isPending}
      />
    </Stack>
  );
}
