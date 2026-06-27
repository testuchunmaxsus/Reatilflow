/**
 * ImportPreviewTable — import uchun tahrirlanadigan preview jadvali.
 *
 * Har satr uchun: nom, SKU, barcode, miqdor, narx, valyuta, muddat.
 * Foydalanuvchi satrni o'chirishi, nom/miqdor/narxni tahrirlashi mumkin.
 * Har satr client_uuid bilan belgilanadi (idempotentlik uchun).
 */

import {
  ActionIcon,
  Badge,
  Group,
  NumberInput,
  ScrollArea,
  Table,
  Text,
  TextInput,
  Tooltip,
} from "@mantine/core";
import { IconTrash } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import type { ParsedRow } from "@/api/import";

export interface EditableRow extends ParsedRow {
  client_uuid: string;
}

interface ImportPreviewTableProps {
  rows: EditableRow[];
  onChange: (rows: EditableRow[]) => void;
}

export function ImportPreviewTable({ rows, onChange }: ImportPreviewTableProps) {
  const { t } = useTranslation();

  function updateRow(idx: number, patch: Partial<EditableRow>) {
    const updated = rows.map((r, i) => (i === idx ? { ...r, ...patch } : r));
    onChange(updated);
  }

  function removeRow(idx: number) {
    onChange(rows.filter((_, i) => i !== idx));
  }

  if (rows.length === 0) {
    return (
      <Text c="dimmed" ta="center" py="md" size="sm">
        {t("import.preview.empty", { defaultValue: "Preview bo'sh — fayl yuklab ko'ring" })}
      </Text>
    );
  }

  return (
    <ScrollArea>
      <Table striped withTableBorder withColumnBorders fz="sm" miw={700}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th w={30}>#</Table.Th>
            <Table.Th w={180}>
              {t("import.preview.col_name", { defaultValue: "Mahsulot nomi" })}
            </Table.Th>
            <Table.Th w={100}>
              {t("import.preview.col_sku", { defaultValue: "SKU" })}
            </Table.Th>
            <Table.Th w={110}>
              {t("import.preview.col_barcode", { defaultValue: "Barcode" })}
            </Table.Th>
            <Table.Th w={90}>
              {t("import.preview.col_qty", { defaultValue: "Miqdor" })}
            </Table.Th>
            <Table.Th w={110}>
              {t("import.preview.col_price", { defaultValue: "Narx" })}
            </Table.Th>
            <Table.Th w={60}>
              {t("import.preview.col_currency", { defaultValue: "Val." })}
            </Table.Th>
            <Table.Th w={120}>
              {t("import.preview.col_expiry", { defaultValue: "Muddat" })}
            </Table.Th>
            <Table.Th w={40}></Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((row, idx) => (
            <Table.Tr key={row.client_uuid}>
              <Table.Td>
                <Group gap={4}>
                  <Text size="xs" c="dimmed">{row.row_index}</Text>
                  {row.confidence !== undefined && row.confidence < 0.7 && (
                    <Tooltip
                      label={t("import.preview.low_confidence", {
                        defaultValue: "AI aniqlik past — tekshiring",
                      })}
                    >
                      <Badge color="yellow" size="xs" variant="light">?</Badge>
                    </Tooltip>
                  )}
                </Group>
              </Table.Td>

              {/* Nom */}
              <Table.Td>
                <TextInput
                  size="xs"
                  value={row.name}
                  onChange={(e) => updateRow(idx, { name: e.currentTarget.value })}
                  error={!row.name.trim() ? t("import.preview.name_required", { defaultValue: "Majburiy" }) : undefined}
                />
              </Table.Td>

              {/* SKU */}
              <Table.Td>
                <TextInput
                  size="xs"
                  value={row.sku ?? ""}
                  onChange={(e) =>
                    updateRow(idx, { sku: e.currentTarget.value || null })
                  }
                />
              </Table.Td>

              {/* Barcode */}
              <Table.Td>
                <TextInput
                  size="xs"
                  value={row.barcode ?? ""}
                  onChange={(e) =>
                    updateRow(idx, { barcode: e.currentTarget.value || null })
                  }
                />
              </Table.Td>

              {/* Miqdor */}
              <Table.Td>
                <NumberInput
                  size="xs"
                  value={row.qty}
                  min={0.001}
                  decimalScale={3}
                  onChange={(v) =>
                    updateRow(idx, { qty: typeof v === "number" ? v : row.qty })
                  }
                  error={row.qty <= 0 ? t("import.preview.qty_positive", { defaultValue: ">0" }) : undefined}
                />
              </Table.Td>

              {/* Narx */}
              <Table.Td>
                <NumberInput
                  size="xs"
                  value={row.price}
                  min={0}
                  decimalScale={2}
                  onChange={(v) =>
                    updateRow(idx, { price: typeof v === "number" ? v : row.price })
                  }
                  error={row.price < 0 ? "< 0" : undefined}
                />
              </Table.Td>

              {/* Valyuta */}
              <Table.Td>
                <Text size="xs" c="dimmed">{row.currency}</Text>
              </Table.Td>

              {/* Muddat */}
              <Table.Td>
                <TextInput
                  size="xs"
                  type="date"
                  value={row.expiry_date ?? ""}
                  onChange={(e) =>
                    updateRow(idx, {
                      expiry_date: e.currentTarget.value || null,
                    })
                  }
                />
              </Table.Td>

              {/* O'chirish */}
              <Table.Td>
                <ActionIcon
                  size="sm"
                  color="red"
                  variant="subtle"
                  onClick={() => removeRow(idx)}
                  aria-label={t("import.preview.remove_row", { defaultValue: "Satrni o'chirish" })}
                >
                  <IconTrash size={14} />
                </ActionIcon>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </ScrollArea>
  );
}
