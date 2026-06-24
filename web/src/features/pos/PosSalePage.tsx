/**
 * PosSalePage — Do'kon POS checkout sahifasi.
 *
 * Xususiyatlar:
 * - Mahsulot qidirish (inventardan, is_expired/is_near_expiry bayroqlar bilan)
 * - Muddati o'tgan mahsulot: QIZIL badge + savatga qo'shish bloklanadi
 * - Muddat yaqin mahsulot: SARIQ ogohlantirish
 * - Savat: qo'shish, miqdor o'zgartirish, olib tashlash
 * - Checkout: to'lov usuli tanlash, tasdiqlash
 * - Server 422 pos.product_expired → foydalanuvchiga aniq xato
 * - <Can permission="pos:create"> — checkout tugmasi
 * - Server-avtoritar narx: klient unit_price bermaydi (faqat product_id + qty)
 */

import {
  Alert,
  Badge,
  Button,
  Card,
  Divider,
  Group,
  Loader,
  NumberInput,
  ScrollArea,
  SegmentedControl,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import {
  IconAlertTriangle,
  IconPlus,
  IconShoppingCart,
  IconTrash,
  IconX,
} from "@tabler/icons-react";
import { useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { notifications } from "@mantine/notifications";
import { Can } from "@/rbac/Can";
import { ApiError } from "@/api/client";
import { useDebounce } from "@/hooks/useDebounce";
import { usePosInventory, useCreatePosSale } from "./api/posApi";
import type { CartItem, PosInventoryItem } from "./types";

// ─── To'lov usullari ──────────────────────────────────────────────────────────

const PAYMENT_METHODS = ["cash", "card"] as const;
type PaymentMethod = (typeof PAYMENT_METHODS)[number];

// ─── Props ────────────────────────────────────────────────────────────────────

interface PosSalePageProps {
  /** Do'kon ID — store roli uchun avtomatik (me.branch_id), admin qo'lda beradi */
  storeId: string;
  /** Sotuv yakunlanganda chaqiriladi (kvitansiya ko'rsatish, ro'yxatga qaytish) */
  onSaleComplete?: (saleId: string) => void;
}

// ─── Mahsulot qidiruv natijasi ─────────────────────────────────────────────────

function InventoryResultRow({
  item,
  onAdd,
}: {
  item: PosInventoryItem;
  onAdd: (item: PosInventoryItem) => void;
}) {
  const { t } = useTranslation();

  const blocked = item.is_expired || item.status === "expired";
  const nearExpiry = item.is_near_expiry && !blocked;

  return (
    <Table.Tr style={{ opacity: blocked ? 0.6 : 1 }}>
      <Table.Td>
        <Stack gap={2}>
          <Text size="sm" fw={500}>
            {item.product_id}
          </Text>
          {blocked && (
            <Badge color="red" size="xs">
              {t("pos.product.expiry_blocked", "Muddati o'tgan — sotish taqiqlangan")}
            </Badge>
          )}
          {nearExpiry && (
            <Badge color="yellow" size="xs">
              {t("pos.expiry.expiring_soon", "Muddat yaqin — {{days}} kun qoldi", {
                days: item.days_to_expiry ?? "?",
              })}
            </Badge>
          )}
        </Stack>
      </Table.Td>
      <Table.Td>
        <Text size="sm">{Number(item.qty).toFixed(2)}</Text>
      </Table.Td>
      <Table.Td>
        {item.expiry_date ? (
          <Text
            size="sm"
            c={blocked ? "red" : nearExpiry ? "yellow.7" : undefined}
            fw={blocked || nearExpiry ? 600 : undefined}
          >
            {item.expiry_date}
          </Text>
        ) : (
          <Text size="sm" c="dimmed">
            —
          </Text>
        )}
      </Table.Td>
      <Table.Td>
        <Tooltip
          label={t(
            "pos.product.expiry_blocked",
            "Muddati o'tgan — sotish taqiqlangan",
          )}
          disabled={!blocked}
        >
          <span>
            <Button
              size="xs"
              leftSection={<IconPlus size={12} />}
              disabled={blocked}
              onClick={() => onAdd(item)}
            >
              {t("pos.product.add_to_cart", "Savatga qo'shish")}
            </Button>
          </span>
        </Tooltip>
      </Table.Td>
    </Table.Tr>
  );
}

// ─── Savat qatori ─────────────────────────────────────────────────────────────

function CartRow({
  item,
  onQtyChange,
  onRemove,
}: {
  item: CartItem;
  onQtyChange: (productId: string, qty: number) => void;
  onRemove: (productId: string) => void;
}) {
  const { t } = useTranslation();

  return (
    <Table.Tr>
      <Table.Td>
        <Stack gap={2}>
          <Text size="sm" fw={500}>
            {item.product_name}
          </Text>
          {item.is_near_expiry && !item.is_expired && (
            <Badge color="yellow" size="xs">
              {t("pos.expiry.expiring_soon", "Muddat yaqin")}
            </Badge>
          )}
        </Stack>
      </Table.Td>
      <Table.Td>
        <NumberInput
          value={item.qty}
          onChange={(val) =>
            onQtyChange(item.product_id, Number(val) || 1)
          }
          min={1}
          step={1}
          size="xs"
          w={80}
          hideControls={false}
        />
      </Table.Td>
      <Table.Td>
        <Button
          size="xs"
          variant="subtle"
          color="red"
          leftSection={<IconTrash size={12} />}
          onClick={() => onRemove(item.product_id)}
        >
          {t("pos.cart.remove", "O'chirish")}
        </Button>
      </Table.Td>
    </Table.Tr>
  );
}

// ─── Asosiy komponent ─────────────────────────────────────────────────────────

export function PosSalePage({ storeId, onSaleComplete }: PosSalePageProps) {
  const { t } = useTranslation();

  // Qidiruv
  const [searchInput, setSearchInput] = useState("");
  const search = useDebounce(searchInput, 300);

  // Savat
  const [cart, setCart] = useState<CartItem[]>([]);

  // To'lov
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>("cash");
  const [customerPhone, setCustomerPhone] = useState("");

  // API
  const { data: inventoryData, isLoading: invLoading } = usePosInventory({
    store_id: storeId,
    limit: 50,
  });

  const createSale = useCreatePosSale();

  // ─── Inventarni qidiruv ────────────────────────────────────────────────────

  const filteredInventory = inventoryData?.items.filter((item) => {
    if (!search) return true;
    return item.product_id.toLowerCase().includes(search.toLowerCase());
  }) ?? [];

  // ─── Savatga qo'shish ─────────────────────────────────────────────────────

  const handleAddToCart = useCallback(
    (item: PosInventoryItem) => {
      if (item.is_expired || item.status === "expired") return;

      setCart((prev) => {
        const exists = prev.find((c) => c.product_id === item.product_id);
        if (exists) {
          return prev.map((c) =>
            c.product_id === item.product_id
              ? { ...c, qty: c.qty + 1 }
              : c,
          );
        }
        return [
          ...prev,
          {
            product_id: item.product_id,
            product_name: item.product_id, // product nomi inventory'da yo'q, ID ishlatamiz
            qty: 1,
            is_expired: item.is_expired,
            is_near_expiry: item.is_near_expiry,
          },
        ];
      });

      notifications.show({
        color: "green",
        message: t("pos.messages.item_added", "Mahsulot savatga qo'shildi"),
        autoClose: 2000,
      });
    },
    [t],
  );

  // ─── Savat miqdor o'zgartirish ────────────────────────────────────────────

  const handleQtyChange = useCallback((productId: string, qty: number) => {
    setCart((prev) =>
      prev.map((c) =>
        c.product_id === productId ? { ...c, qty: Math.max(1, qty) } : c,
      ),
    );
  }, []);

  // ─── Savatdan olib tashlash ───────────────────────────────────────────────

  const handleRemove = useCallback((productId: string) => {
    setCart((prev) => prev.filter((c) => c.product_id !== productId));
    notifications.show({
      color: "orange",
      message: t(
        "pos.messages.item_removed",
        "Mahsulot savatdan olib tashlandi",
      ),
      autoClose: 2000,
    });
  }, [t]);

  // ─── Savatni tozalash ─────────────────────────────────────────────────────

  const handleClearCart = useCallback(() => {
    setCart([]);
  }, []);

  // ─── Checkout ─────────────────────────────────────────────────────────────

  const handleCheckout = async () => {
    if (cart.length === 0) return;

    try {
      const sale = await createSale.mutateAsync({
        store_id: storeId,
        payment_method: paymentMethod,
        lines: cart.map((c) => ({
          product_id: c.product_id,
          qty: c.qty,
        })),
        customer_phone: customerPhone || null,
      });

      notifications.show({
        color: "green",
        title: t("pos.payment.success", "Sotuv muvaffaqiyatli amalga oshirildi"),
        message: `ID: ${sale.id.slice(0, 8)}...`,
        autoClose: 5000,
      });

      setCart([]);
      setCustomerPhone("");
      onSaleComplete?.(sale.id);
    } catch (err: unknown) {
      let message: string;

      if (err instanceof ApiError) {
        // pos.product_expired — maxsus xato
        if (err.envelope.message_key === "pos.product_expired") {
          message = t(
            "pos.expiry.blocked_message",
            "Bu mahsulot muddati o'tganligi sababli sotuvga chiqarilmagan",
          );
        } else if (err.envelope.message_key === "pos.insufficient_inventory") {
          message = t("pos.product.out_of_stock", "Stokda yo'q");
        } else {
          message =
            err.envelope.message ??
            t("errors.unknown", "Noma'lum xato yuz berdi");
        }
      } else {
        message = t("errors.unknown", "Noma'lum xato yuz berdi");
      }

      notifications.show({
        color: "red",
        title: t("errors.unknown", "Xato"),
        message,
        autoClose: 6000,
      });
    }
  };

  return (
    <Group align="flex-start" gap="md">
      {/* Chap panel: inventar qidiruvi */}
      <Stack flex={1} gap="md">
        <Title order={4}>
          {t("pos.product.search_placeholder", "Mahsulot nomi yoki barcode...")}
        </Title>

        <TextInput
          placeholder={t(
            "pos.product.search_placeholder",
            "Mahsulot nomi yoki barcode...",
          )}
          value={searchInput}
          onChange={(e) => setSearchInput(e.currentTarget.value)}
          rightSection={
            searchInput ? (
              <IconX
                size={14}
                style={{ cursor: "pointer" }}
                onClick={() => setSearchInput("")}
              />
            ) : null
          }
        />

        {invLoading ? (
          <Loader size="sm" />
        ) : filteredInventory.length === 0 ? (
          <Text c="dimmed" size="sm">
            {t("pos.product.not_found", "Mahsulot topilmadi")}
          </Text>
        ) : (
          <ScrollArea h={400}>
            <Table highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t("pos.cart.product", "Mahsulot")}</Table.Th>
                  <Table.Th>{t("pos.inventory.qty_in_stock", "Stokdagi miqdor")}</Table.Th>
                  <Table.Th>{t("pos.inventory.expiry_date", "Muddat")}</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {filteredInventory.map((item) => (
                  <InventoryResultRow
                    key={item.id}
                    item={item}
                    onAdd={handleAddToCart}
                  />
                ))}
              </Table.Tbody>
            </Table>
          </ScrollArea>
        )}
      </Stack>

      {/* O'ng panel: savat + to'lov */}
      <Card shadow="sm" padding="md" radius="md" withBorder w={360}>
        <Stack gap="md">
          <Group justify="space-between">
            <Group gap="xs">
              <IconShoppingCart size={20} />
              <Title order={5}>{t("pos.cart.title", "Savat")}</Title>
            </Group>
            {cart.length > 0 && (
              <Button
                size="xs"
                variant="subtle"
                color="gray"
                onClick={handleClearCart}
              >
                {t("pos.cart.clear", "Tozalash")}
              </Button>
            )}
          </Group>

          {cart.length === 0 ? (
            <Text c="dimmed" size="sm" ta="center" py="md">
              {t("pos.cart.empty", "Savat bo'sh")}
            </Text>
          ) : (
            <>
              <ScrollArea h={240}>
                <Table>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>{t("pos.cart.product", "Mahsulot")}</Table.Th>
                      <Table.Th>{t("pos.cart.qty", "Miqdor")}</Table.Th>
                      <Table.Th />
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {cart.map((item) => (
                      <CartRow
                        key={item.product_id}
                        item={item}
                        onQtyChange={handleQtyChange}
                        onRemove={handleRemove}
                      />
                    ))}
                  </Table.Tbody>
                </Table>
              </ScrollArea>

              <Alert
                icon={<IconAlertTriangle size={14} />}
                color="blue"
                variant="light"
              >
                {t(
                  "orders.create.price_note",
                  "Narx va chegirma server tomonida avtomatik hisoblanadi",
                )}
              </Alert>

              <Divider />

              {/* To'lov usuli */}
              <Stack gap="xs">
                <Text size="sm" fw={500}>
                  {t("pos.payment.method", "To'lov usuli")}
                </Text>
                <SegmentedControl
                  value={paymentMethod}
                  onChange={(v) => setPaymentMethod(v as PaymentMethod)}
                  data={[
                    { label: t("pos.payment.cash", "Naqd"), value: "cash" },
                    { label: t("pos.payment.card", "Karta"), value: "card" },
                  ]}
                  fullWidth
                />
              </Stack>

              {/* Telefon (ixtiyoriy) */}
              <TextInput
                label={t("customers.table.phone", "Telefon") + " (" + t("common.cancel", "ixtiyoriy").toLowerCase() + ")"}
                placeholder="+998901234567"
                value={customerPhone}
                onChange={(e) => setCustomerPhone(e.currentTarget.value)}
              />

              {/* Checkout */}
              <Can
                permission="pos:create"
                fallback={
                  <Text c="dimmed" size="sm" ta="center">
                    {t("pos.product.expiry_blocked", "Ruxsat yo'q")}
                  </Text>
                }
              >
                <Button
                  fullWidth
                  size="md"
                  loading={createSale.isPending}
                  onClick={handleCheckout}
                >
                  {t("pos.cart.checkout", "To'lov")}
                </Button>
              </Can>
            </>
          )}
        </Stack>
      </Card>
    </Group>
  );
}
