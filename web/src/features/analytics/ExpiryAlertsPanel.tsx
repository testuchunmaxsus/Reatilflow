/**
 * ExpiryAlertsPanel — Muddati o'tgan/o'tayotgan partiyalar jadvali.
 *
 * Rang belgilari:
 *   - days_left <= 0 → qizil (muddati o'tgan)
 *   - days_left <= 7 → to'q sariq (shoshilinch)
 *   - days_left <= 30 → sariq (ogohlantirish)
 */

import {
  Badge,
  Box,
  Table,
  Text,
} from "@mantine/core";
import { useTranslation } from "react-i18next";
import type { ExpiryItem, ExpiryStatus } from "./types";

interface ExpiryAlertsPanelProps {
  items: ExpiryItem[];
}

function statusColor(status: ExpiryStatus): string {
  if (status === "expired") return "red";
  if (status === "urgent") return "orange";
  return "yellow";
}

function useStatusLabel() {
  const { t } = useTranslation();
  return (status: ExpiryStatus): string => {
    if (status === "expired") return t("analytics.expiry.status_expired", { defaultValue: "Muddati o'tgan" });
    if (status === "urgent") return t("analytics.expiry.status_urgent", { defaultValue: "Shoshilinch" });
    return t("analytics.expiry.status_warning", { defaultValue: "Ogohlantirish" });
  };
}

export function ExpiryAlertsPanel({ items }: ExpiryAlertsPanelProps) {
  const { t } = useTranslation();
  const statusLabel = useStatusLabel();

  if (items.length === 0) {
    return (
      <Box py="md" ta="center">
        <Text c="dimmed" size="sm">
          {t("analytics.expiry.empty", { defaultValue: "Muddati o'tayotgan tovarlar topilmadi" })}
        </Text>
      </Box>
    );
  }

  return (
    <Table.ScrollContainer minWidth={640}>
      <Table striped withTableBorder>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>{t("analytics.expiry.col_store", { defaultValue: "Do'kon" })}</Table.Th>
            <Table.Th>{t("analytics.expiry.col_product", { defaultValue: "Mahsulot" })}</Table.Th>
            <Table.Th ta="right">{t("analytics.expiry.col_qty", { defaultValue: "Miqdor" })}</Table.Th>
            <Table.Th>{t("analytics.expiry.col_expiry_date", { defaultValue: "Muddat" })}</Table.Th>
            <Table.Th ta="right">{t("analytics.expiry.col_days_left", { defaultValue: "Qolgan kun" })}</Table.Th>
            <Table.Th>{t("analytics.expiry.col_status", { defaultValue: "Holat" })}</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {items.map((item, idx) => (
            <Table.Tr key={`${item.store_id}-${item.product_id}-${idx}`}>
              <Table.Td>
                <Text size="sm" fw={500}>{item.store_name}</Text>
              </Table.Td>
              <Table.Td>
                <Text size="sm">{item.product_name}</Text>
              </Table.Td>
              <Table.Td ta="right">
                <Text size="sm">{item.qty}</Text>
              </Table.Td>
              <Table.Td>
                <Text size="sm">{item.expiry_date}</Text>
              </Table.Td>
              <Table.Td ta="right">
                <Text
                  size="sm"
                  fw={600}
                  c={item.days_left <= 0 ? "red" : item.days_left <= 7 ? "orange" : "yellow.7"}
                >
                  {item.days_left <= 0
                    ? t("analytics.expiry.overdue", { defaultValue: "O'tgan" })
                    : item.days_left}
                </Text>
              </Table.Td>
              <Table.Td>
                <Badge color={statusColor(item.status)} variant="light" size="sm">
                  {statusLabel(item.status)}
                </Badge>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}
