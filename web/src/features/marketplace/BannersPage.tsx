/**
 * BannersPage — marketplace banner boshqaruvi.
 *
 * Xususiyatlar:
 * - Banner ro'yxati (jadval): nomi, rasm, holat, tartib
 * - Yaratish / tahrirlash modal (BannerFormModal)
 * - O'chirish tasdiqlash (ConfirmDeleteModal)
 * - RBAC: <Can permission="catalog:edit"> (marketplace uchun alohida ruxsat yo'q)
 * - i18n uz/ru
 *
 * Backend: GET /marketplace/banners/mine?page=1&limit=20 → PaginatedBanners
 * BannerOut: title (bitta), priority, valid_from, valid_to
 */

import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Group,
  Image,
  Loader,
  Pagination,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconEdit, IconPlus, IconTrash } from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Can } from "@/rbac/Can";
import { useApiError } from "@/hooks/useApiError";
import { useBanners, useDeleteBanner } from "./api/marketplaceApi";
import { BannerFormModal } from "./components/BannerFormModal";
import { ConfirmDeleteModal } from "@/components/ConfirmDeleteModal";
import type { BannerOut } from "./types";

const PAGE_SIZE = 20;

export function BannersPage() {
  const { t } = useTranslation();
  const { showError } = useApiError();

  const [page, setPage] = useState(1);
  const offset = (page - 1) * PAGE_SIZE;

  const [formOpened, { open: openForm, close: closeForm }] = useDisclosure(false);
  const [deleteOpened, { open: openDelete, close: closeDelete }] =
    useDisclosure(false);
  const [editingBanner, setEditingBanner] = useState<BannerOut | undefined>(undefined);
  const [deletingBanner, setDeletingBanner] = useState<BannerOut | null>(null);

  const { data, isLoading, isError, error } = useBanners({
    limit: PAGE_SIZE,
    offset,
  });
  const deleteBanner = useDeleteBanner();

  const handleCreateClick = () => {
    setEditingBanner(undefined);
    openForm();
  };

  const handleEditClick = (banner: BannerOut) => {
    setEditingBanner(banner);
    openForm();
  };

  const handleDeleteClick = (banner: BannerOut) => {
    setDeletingBanner(banner);
    openDelete();
  };

  const handleConfirmDelete = async () => {
    if (!deletingBanner) return;
    try {
      await deleteBanner.mutateAsync(deletingBanner.id);
      notifications.show({
        color: "orange",
        message: t("marketplace.banner.messages.deleted"),
      });
      closeDelete();
    } catch (err) {
      showError(err);
    }
  };

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1;

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Title order={3}>{t("marketplace.banners.title")}</Title>
        <Can permission="catalog:edit">
          <Button leftSection={<IconPlus size={16} />} onClick={handleCreateClick}>
            {t("marketplace.banners.actions.create")}
          </Button>
        </Can>
      </Group>

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
          <Text c="dimmed">{t("marketplace.banners.empty")}</Text>
        </Box>
      ) : (
        <Table.ScrollContainer minWidth={700}>
          <Table striped highlightOnHover withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th w={80}>{t("marketplace.banners.table.image")}</Table.Th>
                <Table.Th>{t("marketplace.banners.table.title")}</Table.Th>
                <Table.Th>{t("marketplace.banners.table.target_url")}</Table.Th>
                <Table.Th>{t("marketplace.banners.table.priority")}</Table.Th>
                <Table.Th>{t("marketplace.banners.table.valid_from")}</Table.Th>
                <Table.Th>{t("marketplace.banners.table.valid_to")}</Table.Th>
                <Table.Th>{t("marketplace.banners.table.status")}</Table.Th>
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
                        w={60}
                        h={36}
                        fit="cover"
                        radius="sm"
                      />
                    ) : (
                      <Box w={60} h={36} bg="gray.1" style={{ borderRadius: 4 }} />
                    )}
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" fw={500} lineClamp={1}>
                      {banner.title}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed" lineClamp={1}>
                      {banner.target_url ?? "—"}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{banner.priority}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed">
                      {banner.valid_from}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed">
                      {banner.valid_to}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Badge
                      color={banner.is_active ? "green" : "gray"}
                      variant="light"
                      size="sm"
                    >
                      {banner.is_active
                        ? t("catalog.status.active")
                        : t("catalog.status.inactive")}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Can permission="catalog:edit">
                      <Group gap={4}>
                        <Tooltip label={t("common.edit")}>
                          <ActionIcon
                            variant="subtle"
                            onClick={() => handleEditClick(banner)}
                            aria-label={t("common.edit")}
                          >
                            <IconEdit size={16} />
                          </ActionIcon>
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
                    </Can>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}

      {totalPages > 1 && (
        <Group justify="center">
          <Pagination value={page} onChange={setPage} total={totalPages} size="sm" />
        </Group>
      )}

      <BannerFormModal
        opened={formOpened}
        onClose={closeForm}
        banner={editingBanner}
      />

      <ConfirmDeleteModal
        opened={deleteOpened}
        onClose={closeDelete}
        onConfirm={() => { void handleConfirmDelete(); }}
        title={t("marketplace.banner.delete.title")}
        message={
          deletingBanner
            ? t("marketplace.banner.delete.confirm", {
                name: deletingBanner.title,
              })
            : ""
        }
        loading={deleteBanner.isPending}
      />
    </Stack>
  );
}
