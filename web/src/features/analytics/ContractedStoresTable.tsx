/**
 * ContractedStoresTable — Shartnoma qilgan do'konlar ro'yxati.
 *
 * Ustunlar: Do'kon nomi | Manzil | Shartnoma holati | Muddati | Inventar qoldig'i | 30 kun sotuvi
 * Status badge: active=yashil, expiring=sariq, expired=qizil
 */

import {
  Badge,
  Box,
  Table,
  Text,
} from "@mantine/core";
import { useTranslation } from "react-i18next";
import type { ContractedStoreItem } from "./types";

interface ContractedStoresTableProps {
  stores: ContractedStoreItem[];
}

type ContractStatus = "active" | "expiring" | "expired";

function contractStatusColor(status: ContractStatus): string {
  if (status === "active") return "green";
  if (status === "expiring") return "yellow";
  return "red";
}

function useContractStatusLabel() {
  const { t } = useTranslation();
  return (status: ContractStatus): string => {
    if (status === "active") return t("contracts.status.active", { defaultValue: "Amal qiladi" });
    if (status === "expiring") return t("contracts.status.expiring", { defaultValue: "Tugayotgan" });
    return t("contracts.status.expired", { defaultValue: "Muddati tugagan" });
  };
}

export function ContractedStoresTable({ stores }: ContractedStoresTableProps) {
  const { t } = useTranslation();
  const contractStatusLabel = useContractStatusLabel();

  if (stores.length === 0) {
    return (
      <Box py="md" ta="center">
        <Text c="dimmed" size="sm">
          {t("analytics.stores.empty", { defaultValue: "Shartnoma qilgan do'konlar topilmadi" })}
        </Text>
      </Box>
    );
  }

  return (
    <Table.ScrollContainer minWidth={700}>
      <Table striped withTableBorder>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>{t("analytics.stores.col_name", { defaultValue: "Do'kon" })}</Table.Th>
            <Table.Th>{t("analytics.stores.col_address", { defaultValue: "Manzil" })}</Table.Th>
            <Table.Th>{t("analytics.stores.col_status", { defaultValue: "Shartnoma holati" })}</Table.Th>
            <Table.Th>{t("analytics.stores.col_valid_to", { defaultValue: "Muddati" })}</Table.Th>
            <Table.Th ta="right">{t("analytics.stores.col_inventory", { defaultValue: "Qoldiq (dona)" })}</Table.Th>
            <Table.Th ta="right">{t("analytics.stores.col_sold_30d", { defaultValue: "30 kun sotuv" })}</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {stores.map((store) => (
            <Table.Tr key={store.store_id}>
              <Table.Td>
                <Text size="sm" fw={500}>
                  {store.store_name}
                </Text>
              </Table.Td>
              <Table.Td>
                <Text size="sm" c="dimmed">
                  {store.address ?? "—"}
                </Text>
              </Table.Td>
              <Table.Td>
                <Badge
                  color={contractStatusColor(store.contract_status)}
                  variant="light"
                  size="sm"
                >
                  {contractStatusLabel(store.contract_status)}
                </Badge>
              </Table.Td>
              <Table.Td>
                <Text size="sm">
                  {store.valid_to ? store.valid_to.slice(0, 10) : "—"}
                </Text>
              </Table.Td>
              <Table.Td ta="right">
                <Text size="sm">{store.inventory_qty.toLocaleString()}</Text>
              </Table.Td>
              <Table.Td ta="right">
                <Text size="sm">{store.sold_qty_30d.toLocaleString()}</Text>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}
