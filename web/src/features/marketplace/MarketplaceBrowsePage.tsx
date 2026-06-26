/**
 * MarketplaceBrowsePage — jamlangan katalog browse sahifasi.
 *
 * Cross-tenant: barcha korxonalar marketplace_published=True mahsulotlari.
 * - Mahsulot grid/card: nom, supplier, narx, rasm/SKU
 * - Qidiruv (nom/sku/barcode)
 * - Supplier filtri (GET /marketplace/suppliers)
 * - Pagination
 * - "Buyurtma berish" tugma → CreateMarketplaceOrderModal
 *
 * GET /marketplace/products + GET /marketplace/suppliers
 * POST /marketplace/orders (CreateMarketplaceOrderModal orqali)
 */

import {
  Avatar,
  Badge,
  Box,
  Button,
  Card,
  Center,
  Grid,
  Group,
  Loader,
  Pagination,
  Select,
  Stack,
  Text,
  TextInput,
  Title,
  Image,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { useDebouncedValue } from "@mantine/hooks";
import { IconSearch, IconShoppingCart, IconBox } from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Can } from "@/rbac/Can";
import {
  useMarketplaceProducts,
  useMarketplaceSuppliers,
} from "./api/marketplaceApi";
import {
  CreateMarketplaceOrderModal,
  type OrderLineItem,
} from "./components/CreateMarketplaceOrderModal";
import type { MarketplaceProductOut } from "./types";

const PAGE_SIZE = 20;

// ─── Bitta mahsulot kartasi ───────────────────────────────────────────────────

interface ProductCardProps {
  product: MarketplaceProductOut;
  onOrder: (product: MarketplaceProductOut) => void;
}

function ProductCard({ product, onOrder }: ProductCardProps) {
  const { t } = useTranslation();
  const displayName = product.name || product.name_uz;

  return (
    <Card withBorder radius="sm" p="md" style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      {/* Rasm */}
      <Card.Section mb="xs">
        {product.photo_url ? (
          <Image
            src={product.photo_url}
            height={140}
            alt={displayName}
            fit="cover"
          />
        ) : (
          <Center h={140} bg="gray.0">
            <IconBox size={40} color="var(--mantine-color-gray-4)" />
          </Center>
        )}
      </Card.Section>

      {/* Kontent */}
      <Stack gap={4} style={{ flex: 1 }}>
        <Text size="sm" fw={600} lineClamp={2}>
          {displayName}
        </Text>

        {product.sku && (
          <Text size="xs" c="dimmed">
            SKU: {product.sku}
          </Text>
        )}

        <Group gap={4} mt={2}>
          <Badge size="xs" variant="light" color="blue">
            {product.supplier_name}
          </Badge>
        </Group>

        <Group justify="space-between" mt="auto" pt="xs">
          {product.price != null ? (
            <Text size="sm" fw={700} ff="monospace">
              {Number(product.price).toLocaleString()} UZS
            </Text>
          ) : (
            <Text size="sm" c="dimmed">
              {t("marketplace.browse.no_price", { defaultValue: "Narx yo'q" })}
            </Text>
          )}
          <Text size="xs" c="dimmed">
            {product.unit}
          </Text>
        </Group>
      </Stack>

      {/* Buyurtma berish tugmasi */}
      <Can permission="marketplace:create">
        <Button
          fullWidth
          size="xs"
          mt="xs"
          leftSection={<IconShoppingCart size={14} />}
          onClick={() => onOrder(product)}
        >
          {t("marketplace.browse.order_btn", { defaultValue: "Buyurtma berish" })}
        </Button>
      </Can>
    </Card>
  );
}

// ─── Asosiy sahifa ────────────────────────────────────────────────────────────

export function MarketplaceBrowsePage() {
  const { t } = useTranslation();

  const [searchInput, setSearchInput] = useState("");
  const [debouncedSearch] = useDebouncedValue(searchInput, 350);
  const [supplierFilter, setSupplierFilter] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const [modalOpened, { open: openModal, close: closeModal }] =
    useDisclosure(false);
  const [orderItems, setOrderItems] = useState<OrderLineItem[]>([]);

  // Mahsulotlar
  const { data, isLoading, isError, error } = useMarketplaceProducts({
    search: debouncedSearch || undefined,
    supplier_enterprise: supplierFilter ?? undefined,
    page,
    limit: PAGE_SIZE,
  });

  // Supplierlar (filter uchun)
  const { data: suppliersData } = useMarketplaceSuppliers();

  const supplierOptions = [
    {
      value: "",
      label: t("marketplace.browse.all_suppliers", {
        defaultValue: "Barcha ta'minotchilar",
      }),
    },
    ...(suppliersData?.map((s) => ({
      value: s.enterprise_id,
      label: `${s.name} (${s.product_count})`,
    })) ?? []),
  ];

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1;

  const handleOrderClick = (product: MarketplaceProductOut) => {
    setOrderItems([{ product, qty: 1 }]);
    openModal();
  };

  const handleModalClose = () => {
    setOrderItems([]);
    closeModal();
  };

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Title order={3}>
          {t("marketplace.browse.title", { defaultValue: "Marketplace Katalog" })}
        </Title>
        {data && (
          <Text size="sm" c="dimmed">
            {t("marketplace.browse.total_products", {
              count: data.total,
              defaultValue: `Jami: ${data.total} mahsulot`,
            })}
          </Text>
        )}
      </Group>

      {/* Filtrlar */}
      <Group gap="sm">
        <TextInput
          placeholder={t("marketplace.browse.search_placeholder", {
            defaultValue: "Qidiruv (nom, SKU, barcode)...",
          })}
          leftSection={<IconSearch size={14} />}
          value={searchInput}
          onChange={(e) => {
            setSearchInput(e.currentTarget.value);
            setPage(1);
          }}
          w={280}
          aria-label={t("marketplace.browse.search_placeholder", {
            defaultValue: "Qidiruv",
          })}
        />
        <Select
          data={supplierOptions}
          value={supplierFilter ?? ""}
          onChange={(v) => {
            setSupplierFilter(v || null);
            setPage(1);
          }}
          w={240}
          aria-label={t("marketplace.browse.all_suppliers", {
            defaultValue: "Ta'minotchi filtri",
          })}
          allowDeselect={false}
        />
      </Group>

      {/* Mahsulotlar */}
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
          <Stack align="center" gap="xs">
            <Avatar size="xl" color="gray" variant="light">
              <IconBox size={32} />
            </Avatar>
            <Text c="dimmed" size="sm">
              {t("marketplace.browse.empty", {
                defaultValue: "Mahsulotlar topilmadi",
              })}
            </Text>
          </Stack>
        </Box>
      ) : (
        <Grid gutter="md">
          {data.items.map((product) => (
            <Grid.Col key={product.id} span={{ base: 12, xs: 6, sm: 4, md: 3 }}>
              <ProductCard product={product} onOrder={handleOrderClick} />
            </Grid.Col>
          ))}
        </Grid>
      )}

      {/* Sahifalash */}
      {totalPages > 1 && (
        <Group justify="center">
          <Pagination value={page} onChange={setPage} total={totalPages} size="sm" />
        </Group>
      )}

      {/* Buyurtma berish modali */}
      <CreateMarketplaceOrderModal
        opened={modalOpened}
        onClose={handleModalClose}
        items={orderItems}
      />
    </Stack>
  );
}
