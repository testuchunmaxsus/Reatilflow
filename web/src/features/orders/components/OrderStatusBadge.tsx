/**
 * OrderStatusBadge — buyurtma holati uchun rangli Mantine Badge.
 *
 * Holat ranglari:
 *   draft      → gray
 *   confirmed  → blue
 *   packed     → violet
 *   delivering → orange
 *   delivered  → green
 *   canceled   → red
 */

import { Badge } from "@mantine/core";
import { useTranslation } from "react-i18next";
import type { OrderStatus } from "../types";

interface OrderStatusBadgeProps {
  status: OrderStatus;
  size?: "xs" | "sm" | "md" | "lg" | "xl";
}

const STATUS_COLORS: Record<OrderStatus, string> = {
  draft: "gray",
  confirmed: "blue",
  packed: "violet",
  delivering: "orange",
  delivered: "green",
  canceled: "red",
};

export function OrderStatusBadge({
  status,
  size = "sm",
}: OrderStatusBadgeProps) {
  const { t } = useTranslation();

  return (
    <Badge color={STATUS_COLORS[status]} variant="light" size={size}>
      {t(`orders.status.${status}`)}
    </Badge>
  );
}
