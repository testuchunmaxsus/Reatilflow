/**
 * StockListPage — ombor harakatlari ro'yxati sahifasi.
 *
 * Xususiyatlar:
 * - Paginated jadval (harakat ID, product_id, warehouse_id, tur, miqdor, sana, bajardi)
 * - Filtrlar: movement_type
 * - Qoldiq kartasi: product_id + warehouse_id bo'yicha balans tekshirish
 * - Admin uchun harakat qo'shish tugmasi va modali (<Can permission="stock:create">)
 * - i18n stock.* kalitlari (mavjud + defaultValue fallback)
 * - TanStack Query orqali ma'lumot olish
 */

import {
  Badge,
  Box,
  Button,
  Card,
  Group,
  Loader,
  Pagination,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { IconPlus, IconSearch } from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Can } from "@/rbac/Can";
import { useStockMovements, useStockBalance } from "./api/stockApi";
import { CreateMovementModal } from "./components/CreateMovementModal";
import type { MovementType } from "./types";

const PAGE_SIZE = 20;

// ─── Harakat turi badge rangi ─────────────────────────────────────────────────

const MOVEMENT_TYPE_COLOR: Record<MovementType, string> = {
  in: "green",
  out: "red",
  transfer: "blue",
  adjust: "orange",
};

// ─── Filtr tipi options ───────────────────────────────────────────────────────

const TYPE_OPTIONS = [
  { value: "", labelKey: "stock.filter.all_types" },
  { value: "in", labelKey: "stock.movement.receive" },
  { value: "out", labelKey: "stock.movement.write_off" },
  { value: "transfer", labelKey: "stock.movement.transfer" },
  { value: "adjust", labelKey: "stock.movement_form.type_adjust" },
];

// ─── Komponent ────────────────────────────────────────────────────────────────

export function StockListPage() {
  const { t } = useTranslation();

  // Harakat turi filtri
  const [typeFilter, setTypeFilter] = useState<MovementType | null>(null);

  // Sahifalash
  const [page, setPage] = useState(1);
  const offset = (page - 1) * PAGE_SIZE;

  // Qoldiq tekshirish uchun maydonlar
  const [balanceProductId, setBalanceProductId] = useState("");
  const [balanceWarehouseId, setBalanceWarehouseId] = useState("");
  const [balanceQuery, setBalanceQuery] = useState<{
    productId: string;
    warehouseId: string;
  } | null>(null);

  // Modal holati
  const [createOpened, { open: openCreate, close: closeCreate }] =
    useDisclosure(false);

  // Harakatlar ro'yxati so'rovi
  const { data, isLoading, isError, error } = useStockMovements({
    movement_type: typeFilter,
    limit: PAGE_SIZE,
    offset,
  });

  // Qoldiq so'rovi (faqat yetarli ID bo'lsa)
  const { data: balanceData, isLoading: balanceLoading } = useStockBalance(
    balanceQuery?.productId ?? "",
    balanceQuery?.warehouseId ?? "",
    balanceQuery !== null,
  );

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1;

  function handleBalanceSearch() {
    const uuidRegex =
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (
      uuidRegex.test(balanceProductId.trim()) &&
      uuidRegex.test(balanceWarehouseId.trim())
    ) {
      setBalanceQuery({
        productId: balanceProductId.trim(),
        warehouseId: balanceWarehouseId.trim(),
      });
    }
  }

  return (
    <Stack gap="md">
      {/* Sarlavha va yaratish tugmasi */}
      <Group justify="space-between">
        <Title order={3}>
          {t("stock.title", { defaultValue: "Ombor" })}
        </Title>
        <Can permission="stock:create">
          <Button leftSection={<IconPlus size={16} />} onClick={openCreate}>
            {t("stock.actions.add_movement", {
              defaultValue: "Harakat qo'shish",
            })}
          </Button>
        </Can>
      </Group>

      {/* Qoldiq tekshirish kartasi */}
      <Card withBorder padding="md" radius="sm">
        <Text fw={500} mb="sm">
          {t("stock.balance.title", { defaultValue: "Qoldiq tekshirish" })}
        </Text>
        <Group gap="sm" wrap="wrap" align="flex-end">
          <TextInput
            label={t("stock.balance.product_id", {
              defaultValue: "Mahsulot ID (UUID)",
            })}
            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            value={balanceProductId}
            onChange={(e) => setBalanceProductId(e.currentTarget.value)}
            w={300}
          />
          <TextInput
            label={t("stock.balance.warehouse_id", {
              defaultValue: "Ombor ID (UUID)",
            })}
            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            value={balanceWarehouseId}
            onChange={(e) => setBalanceWarehouseId(e.currentTarget.value)}
            w={300}
          />
          <Button
            leftSection={<IconSearch size={14} />}
            onClick={handleBalanceSearch}
            loading={balanceLoading}
            variant="light"
          >
            {t("stock.balance.check", { defaultValue: "Tekshirish" })}
          </Button>
        </Group>

        {/* Qoldiq natijasi */}
        {balanceData && (
          <Group gap="xl" mt="md">
            <Box>
              <Text size="xs" c="dimmed">
                {t("stock.balance.qty_on_hand", {
                  defaultValue: "Mavjud miqdor",
                })}
              </Text>
              <Text fw={700} size="lg">
                {Number(balanceData.qty_on_hand).toLocaleString()}
              </Text>
            </Box>
            <Box>
              <Text size="xs" c="dimmed">
                {t("stock.balance.qty_reserved", {
                  defaultValue: "Band miqdor",
                })}
              </Text>
              <Text fw={500} size="lg" c="orange">
                {Number(balanceData.qty_reserved).toLocaleString()}
              </Text>
            </Box>
            <Box>
              <Text size="xs" c="dimmed">
                {t("stock.balance.updated_at", {
                  defaultValue: "Yangilangan",
                })}
              </Text>
              <Text size="sm">
                {new Date(balanceData.updated_at).toLocaleString()}
              </Text>
            </Box>
          </Group>
        )}
      </Card>

      {/* Filtrlar */}
      <Group gap="sm" wrap="wrap">
        <Select
          placeholder={t("stock.filter.all_types", {
            defaultValue: "Barcha turlar",
          })}
          data={TYPE_OPTIONS.map((o) => ({
            value: o.value,
            label: t(o.labelKey, { defaultValue: o.value || "Barcha turlar" }),
          }))}
          value={typeFilter ?? ""}
          onChange={(v) => {
            setTypeFilter((v as MovementType) || null);
            setPage(1);
          }}
          w={180}
          clearable
          aria-label={t("stock.filter.all_types", {
            defaultValue: "Harakat turi",
          })}
        />
      </Group>

      {/* Jadval */}
      {isLoading ? (
        <Group justify="center" py="xl">
          <Loader />
          <Text c="dimmed">
            {t("common.loading", { defaultValue: "Yuklanmoqda..." })}
          </Text>
        </Group>
      ) : isError ? (
        <Box py="xl" ta="center">
          <Text c="red">
            {error instanceof Error
              ? error.message
              : t("errors.unknown", { defaultValue: "Xato yuz berdi" })}
          </Text>
        </Box>
      ) : !data?.items.length ? (
        <Box py="xl" ta="center">
          <Text c="dimmed">
            {t("stock.movement.empty", {
              defaultValue: "Harakat yozuvlari topilmadi",
            })}
          </Text>
        </Box>
      ) : (
        <Table.ScrollContainer minWidth={800}>
          <Table striped highlightOnHover withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>ID</Table.Th>
                <Table.Th>
                  {t("stock.table.product", { defaultValue: "Mahsulot" })}
                </Table.Th>
                <Table.Th>
                  {t("stock.movement.type", { defaultValue: "Tur" })}
                </Table.Th>
                <Table.Th ta="right">
                  {t("stock.movement.qty", { defaultValue: "Miqdor" })}
                </Table.Th>
                <Table.Th>
                  {t("stock.movement.date", { defaultValue: "Sana" })}
                </Table.Th>
                <Table.Th>
                  {t("stock.movement_form.ref_type", {
                    defaultValue: "Havola turi",
                  })}
                </Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.items.map((movement) => (
                <Table.Tr key={movement.id}>
                  <Table.Td>
                    <Text size="sm" ff="monospace">
                      {movement.id.slice(0, 8).toUpperCase()}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" ff="monospace">
                      {movement.product_id.slice(0, 8)}...
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Badge
                      color={MOVEMENT_TYPE_COLOR[movement.type] ?? "gray"}
                      variant="light"
                      size="sm"
                    >
                      {movement.type.toUpperCase()}
                    </Badge>
                  </Table.Td>
                  <Table.Td ta="right">
                    <Text size="sm" fw={500}>
                      {Number(movement.qty).toLocaleString()}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">
                      {new Date(movement.moved_at).toLocaleString()}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed">
                      {movement.ref_type ?? "—"}
                    </Text>
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

      {/* Harakat yaratish modali */}
      <CreateMovementModal opened={createOpened} onClose={closeCreate} />
    </Stack>
  );
}
