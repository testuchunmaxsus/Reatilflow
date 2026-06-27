/**
 * ProductRankingChart — Recharts BarChart: top/bottom mahsulotlar.
 *
 * Toggle: "Eng ko'p sotiladigan" / "Eng kam sotiladigan"
 * X-o'q: mahsulot nomi (qisqartirilgan)
 * Y-o'q: sotilgan miqdor
 *
 * Maydon nomlari: ProductRankingItem (backend ProductRankingItem bilan mos).
 * Props: products = ProductRankingOut.items (backend: items, eski "products" emas).
 */

import {
  Box,
  SegmentedControl,
  Text,
} from "@mantine/core";
import { useTranslation } from "react-i18next";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import type { ProductRankingItem, ProductOrder } from "./types";

interface ProductRankingChartProps {
  products: ProductRankingItem[];
  order: ProductOrder;
  onOrderChange: (order: ProductOrder) => void;
}

function shortenName(name: string, max = 12): string {
  return name.length > max ? name.slice(0, max) + "…" : name;
}

export function ProductRankingChart({
  products,
  order,
  onOrderChange,
}: ProductRankingChartProps) {
  const { t } = useTranslation();

  const chartData = (products ?? []).map((p) => ({
    name: shortenName(p.product_name ?? ""),
    fullName: p.product_name ?? "",
    sold_qty: p.sold_qty ?? 0,
    revenue: Number(p.revenue ?? 0),
    store_count: p.store_count ?? 0,
  }));

  return (
    <Box>
      <SegmentedControl
        value={order}
        onChange={(v) => onOrderChange(v as ProductOrder)}
        data={[
          {
            value: "top",
            label: t("analytics.products.order_top", { defaultValue: "Eng ko'p" }),
          },
          {
            value: "bottom",
            label: t("analytics.products.order_bottom", { defaultValue: "Eng kam" }),
          },
        ]}
        mb="md"
        size="sm"
      />

      {chartData.length === 0 ? (
        <Box py="md" ta="center">
          <Text c="dimmed" size="sm">
            {t("analytics.products.empty", { defaultValue: "Ma'lumotlar topilmadi" })}
          </Text>
        </Box>
      ) : (
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <RechartsTooltip
              formatter={(value, name) => {
                if (name === "sold_qty")
                  return [
                    value,
                    t("analytics.products.col_sold_qty", { defaultValue: "Sotilgan" }),
                  ];
                if (name === "store_count")
                  return [
                    value,
                    t("analytics.products.col_store_count", { defaultValue: "Do'konlar" }),
                  ];
                return [value, name];
              }}
              labelFormatter={(label) => {
                const found = chartData.find((d) => d.name === label);
                return found?.fullName ?? label;
              }}
            />
            <Legend
              formatter={(value) => {
                if (value === "sold_qty")
                  return t("analytics.products.col_sold_qty", { defaultValue: "Sotilgan" });
                if (value === "store_count")
                  return t("analytics.products.col_store_count", { defaultValue: "Do'konlar soni" });
                return value;
              }}
            />
            <Bar
              dataKey="sold_qty"
              name="sold_qty"
              fill={order === "top" ? "#51cf66" : "#ff6b6b"}
            />
            <Bar dataKey="store_count" name="store_count" fill="#339af0" />
          </BarChart>
        </ResponsiveContainer>
      )}
    </Box>
  );
}
