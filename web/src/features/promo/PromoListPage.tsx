/**
 * PromoListPage — aksiyalar boshqaruv sahifasi.
 *
 * Xususiyatlar:
 * - Paginated jadval — server-side
 * - Filtrlar: is_active, promo_type
 * - RBAC: barcha rollar ko'radi; faqat administrator yaratadi/tahrirlaydi/o'chiradi
 * - Yaratish / tahrirlash modal (PromoFormModal)
 * - O'chirish tasdiqlash (ConfirmDeleteModal — faqat administrator)
 * - is_active badge
 * - rule_json (discount_percent/amount, min_qty) ko'rsatiladi
 * - SERVER-AVTORITAR: discount UI da hisoblanmaydi
 * - i18n uz/ru
 */

import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Group,
  Loader,
  Pagination,
  Select,
  Stack,
  Switch,
  Table,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import { IconEdit, IconPhoto, IconPlus, IconTrash } from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { Can } from "@/rbac/Can";
import { useEnterprise } from "@/enterprise/EnterpriseContext";
import { usePromos, useDeletePromo } from "./api/promoApi";
import { useToggleMarketplaceFeatured } from "@/features/marketplace/api/marketplaceApi";
import { PromoFormModal } from "./components/PromoFormModal";
import { PromoBannerUploadModal } from "./components/PromoBannerUploadModal";
import { ConfirmDeleteModal } from "@/components/ConfirmDeleteModal";
import { useApiError } from "@/hooks/useApiError";
import type { PromoOut, PromoFilters, RuleJson } from "./types";

const PAGE_SIZE = 20;

// ─── rule_json dan o'qilgan chegirma matni ────────────────────────────────────

function ruleLabel(rule: RuleJson): string {
  if (rule.discount_percent !== undefined) {
    return `${rule.discount_percent}%`;
  }
  if (rule.discount_amount !== undefined) {
    return `${rule.discount_amount.toLocaleString()} UZS`;
  }
  return "—";
}

// ─── Komponent ────────────────────────────────────────────────────────────────

export function PromoListPage() {
  const { t } = useTranslation();
  const { showError } = useApiError();
  const { hasModule } = useEnterprise();
  const hasMarketplace = hasModule("marketplace");

  const toggleFeatured = useToggleMarketplaceFeatured();

  const handleFeaturedToggle = async (promo: PromoOut, featured: boolean) => {
    try {
      await toggleFeatured.mutateAsync({
        id: promo.id,
        payload: { featured: featured },
      });
      notifications.show({
        color: featured ? "teal" : "gray",
        message: featured
          ? t("marketplace.featured.enabled")
          : t("marketplace.featured.disabled"),
      });
    } catch (err) {
      showError(err);
    }
  };

  // Filtrlar
  const [activeFilter, setActiveFilter] = useState<"" | "true" | "false">("");
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [page, setPage] = useState(1);
  const offset = (page - 1) * PAGE_SIZE;

  // Modal holatlari
  const [formOpened, { open: openForm, close: closeForm }] =
    useDisclosure(false);
  const [deleteOpened, { open: openDelete, close: closeDelete }] =
    useDisclosure(false);
  const [bannerOpened, { open: openBanner, close: closeBanner }] =
    useDisclosure(false);

  const [editingPromo, setEditingPromo] = useState<PromoOut | undefined>(
    undefined,
  );
  const [deletingPromo, setDeletingPromo] = useState<PromoOut | null>(null);
  const [bannerPromo, setBannerPromo] = useState<PromoOut | null>(null);

  // Filtr params
  const filters: PromoFilters = {
    ...(activeFilter === "true" ? { is_active: true } : {}),
    ...(activeFilter === "false" ? { is_active: false } : {}),
    ...(typeFilter ? { promo_type: typeFilter } : {}),
    limit: PAGE_SIZE,
    offset,
  };

  const { data, isLoading, isError, error } = usePromos(filters);
  const deletePromo = useDeletePromo();

  const handleCreateClick = () => {
    setEditingPromo(undefined);
    openForm();
  };

  const handleEditClick = (promo: PromoOut) => {
    setEditingPromo(promo);
    openForm();
  };

  const handleDeleteClick = (promo: PromoOut) => {
    setDeletingPromo(promo);
    openDelete();
  };

  const handleBannerClick = (promo: PromoOut) => {
    setBannerPromo(promo);
    openBanner();
  };

  const handleConfirmDelete = async () => {
    if (!deletingPromo) return;
    try {
      await deletePromo.mutateAsync(deletingPromo.id);
      notifications.show({
        color: "orange",
        message: t("promo.messages.deleted"),
      });
      closeDelete();
    } catch (err) {
      showError(err);
    }
  };

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1;

  const activeOptions = [
    { value: "", label: t("promo.filter.all") },
    { value: "true", label: t("promo.filter.active_only") },
    { value: "false", label: t("promo.filter.inactive_only") },
  ];

  const typeOptions = [
    { value: "", label: t("promo.filter.all_types") },
    { value: "discount", label: t("promo.type.discount") },
    { value: "bonus", label: t("promo.type.bonus") },
    { value: "gift", label: t("promo.type.gift") },
  ];

  return (
    <Can
      permission="promo:view"
      fallback={
        <Box py="xl" ta="center">
          <Text c="dimmed">{t("promo.access_denied")}</Text>
        </Box>
      }
    >
      <Stack gap="md">
        {/* Sarlavha va yaratish tugmasi */}
        <Group justify="space-between">
          <Title order={3}>{t("pages.promo.title")}</Title>
          <Can permission="promo:create">
            <Button
              leftSection={<IconPlus size={16} />}
              onClick={handleCreateClick}
            >
              {t("promo.actions.create")}
            </Button>
          </Can>
        </Group>

        {/* Filtrlar */}
        <Group gap="sm" wrap="wrap">
          <Select
            data={activeOptions}
            value={activeFilter}
            onChange={(v) => {
              setActiveFilter((v ?? "") as "" | "true" | "false");
              setPage(1);
            }}
            w={180}
            aria-label={t("promo.filter.status")}
            allowDeselect={false}
          />
          <Select
            data={typeOptions}
            value={typeFilter}
            onChange={(v) => {
              setTypeFilter(v ?? "");
              setPage(1);
            }}
            w={160}
            aria-label={t("promo.filter.type")}
            allowDeselect={false}
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
            <Text c="dimmed">{t("promo.table.empty")}</Text>
          </Box>
        ) : (
          <Table.ScrollContainer minWidth={1000}>
            <Table striped highlightOnHover withTableBorder>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t("promo.table.name")}</Table.Th>
                  <Table.Th>{t("promo.table.type")}</Table.Th>
                  <Table.Th>{t("promo.table.discount")}</Table.Th>
                  <Table.Th>{t("promo.table.valid_from")}</Table.Th>
                  <Table.Th>{t("promo.table.valid_to")}</Table.Th>
                  <Table.Th>{t("promo.table.status")}</Table.Th>
                  {hasMarketplace && (
                    <Table.Th>{t("marketplace.featured.column_label")}</Table.Th>
                  )}
                  <Table.Th>{t("catalog.table.actions")}</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {data.items.map((promo) => (
                  <Table.Tr key={promo.id}>
                    <Table.Td>
                      <Text size="sm" fw={500} lineClamp={1}>
                        {/* Lokalizatsiyalangan nom — backend qaytargan name */}
                        {promo.name || promo.name_uz}
                      </Text>
                      {promo.name_ru && promo.name_uz !== promo.name_ru && (
                        <Text size="xs" c="dimmed" lineClamp={1}>
                          {promo.name_uz === promo.name
                            ? promo.name_ru
                            : promo.name_uz}
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <Badge variant="outline" size="sm" color="violet">
                        {t(`promo.type.${promo.promo_type}`)}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" ff="monospace">
                        {ruleLabel(promo.rule_json)}
                        {promo.rule_json.min_qty
                          ? ` (min ${promo.rule_json.min_qty})`
                          : ""}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">{promo.valid_from}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">{promo.valid_to}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Badge
                        color={promo.is_active ? "green" : "gray"}
                        variant="dot"
                        size="sm"
                      >
                        {promo.is_active
                          ? t("promo.status.active")
                          : t("promo.status.inactive")}
                      </Badge>
                    </Table.Td>
                    {hasMarketplace && (
                      <Table.Td>
                        <Can permission="promo:edit">
                          <Switch
                            size="sm"
                            checked={promo.is_marketplace_featured ?? false}
                            onChange={(e) => {
                              void handleFeaturedToggle(promo, e.currentTarget.checked);
                            }}
                            aria-label={t("marketplace.featured.toggle_label")}
                          />
                        </Can>
                      </Table.Td>
                    )}
                    <Table.Td>
                      <Group gap={4}>
                        <Can permission="promo:edit">
                          <Tooltip label={t("common.edit")}>
                            <ActionIcon
                              variant="subtle"
                              onClick={() => handleEditClick(promo)}
                              aria-label={t("common.edit")}
                            >
                              <IconEdit size={16} />
                            </ActionIcon>
                          </Tooltip>
                          <Tooltip
                            label={t("promo.banner.upload", {
                              defaultValue: "Banner yuklash",
                            })}
                          >
                            <ActionIcon
                              variant="subtle"
                              color="grape"
                              onClick={() => handleBannerClick(promo)}
                              aria-label={t("promo.banner.upload", {
                                defaultValue: "Banner yuklash",
                              })}
                            >
                              <IconPhoto size={16} />
                            </ActionIcon>
                          </Tooltip>
                        </Can>
                        <Can permission="promo:delete">
                          <Tooltip label={t("common.delete")}>
                            <ActionIcon
                              variant="subtle"
                              color="red"
                              onClick={() => handleDeleteClick(promo)}
                              aria-label={t("common.delete")}
                            >
                              <IconTrash size={16} />
                            </ActionIcon>
                          </Tooltip>
                        </Can>
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

        {/* Modallar */}
        <PromoFormModal
          opened={formOpened}
          onClose={closeForm}
          promo={editingPromo}
        />
        <PromoBannerUploadModal
          opened={bannerOpened}
          onClose={closeBanner}
          promo={bannerPromo}
        />
        <ConfirmDeleteModal
          opened={deleteOpened}
          onClose={closeDelete}
          onConfirm={() => { void handleConfirmDelete(); }}
          title={t("promo.delete.title")}
          message={
            deletingPromo
              ? t("promo.delete.confirm", {
                  name: deletingPromo.name || deletingPromo.name_uz,
                })
              : ""
          }
          loading={deletePromo.isPending}
        />
      </Stack>
    </Can>
  );
}
