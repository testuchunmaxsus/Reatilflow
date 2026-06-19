/**
 * PriceHistoryModal — mahsulot narx tarixini ko'rsatuvchi modal.
 *
 * GET /catalog/products/{id}/price-history
 */

import {
  Badge,
  Group,
  Loader,
  Modal,
  Stack,
  Table,
  Text,
} from "@mantine/core";
import { useTranslation } from "react-i18next";
import { usePriceHistory } from "../api/catalogApi";
import type { ProductOut } from "@/api/types";

interface PriceHistoryModalProps {
  opened: boolean;
  onClose: () => void;
  product: ProductOut | null;
}

export function PriceHistoryModal({
  opened,
  onClose,
  product,
}: PriceHistoryModalProps) {
  const { t } = useTranslation();
  const { data: history, isLoading } = usePriceHistory(
    product?.id ?? "",
    opened && Boolean(product),
  );

  const formatPrice = (price: string | null) =>
    price
      ? new Intl.NumberFormat("uz-UZ", {
          style: "decimal",
          minimumFractionDigits: 0,
        }).format(Number(price))
      : "—";

  const formatDate = (dateStr: string) =>
    new Date(dateStr).toLocaleString("uz-UZ", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={
        <Text fw={600}>
          {t("catalog.price_history.title")}
          {product && (
            <Text component="span" c="dimmed" size="sm" ml="xs">
              — {product.name_uz}
            </Text>
          )}
        </Text>
      }
      size="xl"
      centered
    >
      {isLoading ? (
        <Group justify="center" py="xl">
          <Loader />
        </Group>
      ) : !history?.length ? (
        <Stack align="center" py="xl">
          <Text c="dimmed">{t("catalog.price_history.empty")}</Text>
        </Stack>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t("catalog.price_history.old_price")}</Table.Th>
              <Table.Th>{t("catalog.price_history.new_price")}</Table.Th>
              <Table.Th>{t("catalog.price_history.currency")}</Table.Th>
              <Table.Th>{t("catalog.price_history.changed_at")}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {history.map((h) => (
              <Table.Tr key={h.id}>
                <Table.Td>
                  <Text size="sm" c="dimmed">
                    {formatPrice(h.old_price)}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" fw={500}>
                    {formatPrice(h.new_price)}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Badge variant="light" size="sm">
                    {h.currency}
                  </Badge>
                </Table.Td>
                <Table.Td>
                  <Text size="sm">{formatDate(h.changed_at)}</Text>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Modal>
  );
}
