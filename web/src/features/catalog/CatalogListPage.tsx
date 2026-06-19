/**
 * CatalogListPage — mahsulotlar ro'yxati sahifasi.
 *
 * Xususiyatlar:
 * - Paginated jadval (Mantine Table)
 * - Qidiruv debounce (300ms)
 * - Filter: is_active, category_id
 * - RBAC: yaratish/tahrirlash/o'chirish tugmalari <Can> bilan
 * - i18n uz/ru (jadval sarlavhalari, tugmalar)
 * - Loading / empty / error holatlari
 * - Narx tarixi ko'rish modal
 * - Rasm yuklash modal
 */

import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Checkbox,
  Group,
  Image,
  Loader,
  Pagination,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import {
  IconEdit,
  IconHistory,
  IconPhoto,
  IconPlus,
  IconSearch,
  IconTrash,
} from "@tabler/icons-react";
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { Can } from "@/rbac/Can";
import { useCategories, useDeleteProduct, useProducts } from "./api/catalogApi";
import { ProductFormModal } from "./components/ProductFormModal";
import { PriceHistoryModal } from "./components/PriceHistoryModal";
import { PhotoUploadModal } from "./components/PhotoUploadModal";
import { ConfirmDeleteModal } from "@/components/ConfirmDeleteModal";
import { useApiError } from "@/hooks/useApiError";
import { useDebounce } from "@/hooks/useDebounce";
import type { ProductOut } from "@/api/types";

const PAGE_SIZE = 20;

// ─── Komponent ────────────────────────────────────────────────────────────────

export function CatalogListPage() {
  const { t, i18n } = useTranslation();
  const { showError } = useApiError();

  // Qidiruv
  const [searchInput, setSearchInput] = useState("");
  const search = useDebounce(searchInput, 300);

  // Filter holatlari
  const [isActiveFilter, setIsActiveFilter] = useState<boolean | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null);

  // Sahifalash
  const [page, setPage] = useState(1);
  const offset = (page - 1) * PAGE_SIZE;

  // Modal holatlari
  const [formOpened, { open: openForm, close: closeForm }] = useDisclosure(false);
  const [historyOpened, { open: openHistory, close: closeHistory }] = useDisclosure(false);
  const [photoOpened, { open: openPhoto, close: closePhoto }] = useDisclosure(false);
  const [deleteOpened, { open: openDelete, close: closeDelete }] = useDisclosure(false);
  const [editingProduct, setEditingProduct] = useState<ProductOut | undefined>(undefined);
  const [selectedProduct, setSelectedProduct] = useState<ProductOut | null>(null);
  const [deletingProduct, setDeletingProduct] = useState<ProductOut | null>(null);

  // API
  const { data, isLoading, isError, error } = useProducts({
    search: search || undefined,
    is_active: isActiveFilter,
    category_id: categoryFilter || undefined,
    limit: PAGE_SIZE,
    offset,
  });

  const { data: categories = [] } = useCategories();
  const deleteProduct = useDeleteProduct();

  // Search input o'zgarsa sahifani birinchiga qaytaramiz
  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchInput(e.target.value);
    setPage(1);
  };

  const handleCreateClick = () => {
    setEditingProduct(undefined);
    openForm();
  };

  const handleEditClick = (product: ProductOut) => {
    setEditingProduct(product);
    openForm();
  };

  const handleHistoryClick = (product: ProductOut) => {
    setSelectedProduct(product);
    openHistory();
  };

  const handlePhotoClick = (product: ProductOut) => {
    setSelectedProduct(product);
    openPhoto();
  };

  const handleDeleteClick = (product: ProductOut) => {
    setDeletingProduct(product);
    openDelete();
  };

  const handleConfirmDelete = async () => {
    if (!deletingProduct) return;
    try {
      await deleteProduct.mutateAsync(deletingProduct.id);
      notifications.show({
        color: "green",
        message: t("catalog.messages.product_deleted"),
      });
      closeDelete();
    } catch (err) {
      showError(err);
    }
  };

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1;

  const localizedName = useCallback(
    (product: ProductOut) =>
      i18n.language === "ru" ? product.name_ru || product.name_uz : product.name_uz,
    [i18n.language],
  );

  const categoryOptions = [
    { value: "", label: t("catalog.filter.all_categories") },
    ...categories.map((c) => ({ value: c.id, label: c.name_uz })),
  ];

  return (
    <Stack gap="md">
      {/* Sarlavha va yaratish tugmasi */}
      <Group justify="space-between">
        <Title order={3}>{t("pages.catalog.title")}</Title>
        <Can permission="catalog:create">
          <Button leftSection={<IconPlus size={16} />} onClick={handleCreateClick}>
            {t("catalog.actions.create")}
          </Button>
        </Can>
      </Group>

      {/* Filtr va qidiruv */}
      <Group gap="sm" wrap="wrap">
        <TextInput
          placeholder={t("catalog.filter.search_placeholder")}
          leftSection={<IconSearch size={16} />}
          value={searchInput}
          onChange={handleSearchChange}
          w={280}
          aria-label={t("catalog.filter.search_placeholder")}
        />
        <Select
          placeholder={t("catalog.filter.all_categories")}
          data={categoryOptions}
          value={categoryFilter ?? ""}
          onChange={(v) => {
            setCategoryFilter(v || null);
            setPage(1);
          }}
          w={200}
          clearable
        />
        <Checkbox
          label={t("catalog.filter.only_active")}
          checked={isActiveFilter === true}
          onChange={(e) => {
            setIsActiveFilter(e.currentTarget.checked ? true : null);
            setPage(1);
          }}
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
          <Text c="dimmed">{t("catalog.table.empty")}</Text>
        </Box>
      ) : (
        <Table.ScrollContainer minWidth={700}>
          <Table striped highlightOnHover withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th w={40}></Table.Th>
                <Table.Th>{t("catalog.table.name")}</Table.Th>
                <Table.Th>{t("catalog.table.sku")}</Table.Th>
                <Table.Th>{t("catalog.table.barcode")}</Table.Th>
                <Table.Th>{t("catalog.table.unit")}</Table.Th>
                <Table.Th>{t("catalog.table.status")}</Table.Th>
                <Table.Th>{t("catalog.table.actions")}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.items.map((product) => (
                <Table.Tr key={product.id}>
                  <Table.Td>
                    {product.photo_url ? (
                      <Image
                        src={product.photo_url}
                        w={36}
                        h={36}
                        fit="cover"
                        radius="sm"
                      />
                    ) : (
                      <Box
                        w={36}
                        h={36}
                        bg="gray.1"
                        style={{ borderRadius: 4 }}
                      />
                    )}
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" fw={500} lineClamp={1}>
                      {localizedName(product)}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" ff="monospace">
                      {product.sku}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" ff="monospace" c="dimmed">
                      {product.barcode ?? "—"}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{product.unit}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Badge
                      color={product.is_active ? "green" : "gray"}
                      variant="light"
                      size="sm"
                    >
                      {product.is_active
                        ? t("catalog.status.active")
                        : t("catalog.status.inactive")}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Group gap={4}>
                      <Tooltip label={t("catalog.actions.price_history")}>
                        <ActionIcon
                          variant="subtle"
                          color="blue"
                          onClick={() => handleHistoryClick(product)}
                          aria-label={t("catalog.actions.price_history")}
                        >
                          <IconHistory size={16} />
                        </ActionIcon>
                      </Tooltip>
                      <Can permission="catalog:edit">
                        <Tooltip label={t("catalog.actions.photo")}>
                          <ActionIcon
                            variant="subtle"
                            color="teal"
                            onClick={() => handlePhotoClick(product)}
                            aria-label={t("catalog.actions.photo")}
                          >
                            <IconPhoto size={16} />
                          </ActionIcon>
                        </Tooltip>
                        <Tooltip label={t("common.edit")}>
                          <ActionIcon
                            variant="subtle"
                            onClick={() => handleEditClick(product)}
                            aria-label={t("common.edit")}
                          >
                            <IconEdit size={16} />
                          </ActionIcon>
                        </Tooltip>
                      </Can>
                      <Can permission="catalog:delete">
                        <Tooltip label={t("common.delete")}>
                          <ActionIcon
                            variant="subtle"
                            color="red"
                            onClick={() => handleDeleteClick(product)}
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
      <ProductFormModal
        opened={formOpened}
        onClose={closeForm}
        product={editingProduct}
      />
      <PriceHistoryModal
        opened={historyOpened}
        onClose={closeHistory}
        product={selectedProduct}
      />
      <PhotoUploadModal
        opened={photoOpened}
        onClose={closePhoto}
        product={selectedProduct}
      />
      <ConfirmDeleteModal
        opened={deleteOpened}
        onClose={closeDelete}
        onConfirm={() => { void handleConfirmDelete(); }}
        title={t("catalog.delete.title")}
        message={
          deletingProduct
            ? t("catalog.delete.confirm", { name: deletingProduct.name_uz })
            : ""
        }
        loading={deleteProduct.isPending}
      />
    </Stack>
  );
}
