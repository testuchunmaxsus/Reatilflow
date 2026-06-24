/**
 * DeliveryStatusBadge — yetkazish holati badge komponenti.
 *
 * FIX #11: DeliveryListPage va DeliveryDetailPage da takrorlangan edi.
 * Bitta umumiy komponent sifatida chiqarildi.
 *
 * Farq: DeliveryListPage variant="light", DeliveryDetailPage variant="filled" ishlatgan.
 * variant prop orqali moslashuvchan.
 */

import { Badge } from "@mantine/core";
import { useTranslation } from "react-i18next";
import type { DeliveryStatus } from "../types";

const COLOR_MAP: Record<string, string> = {
  assigned: "blue",
  started: "cyan",
  delivering: "teal",
  delivered: "green",
  failed: "red",
};

interface DeliveryStatusBadgeProps {
  status: DeliveryStatus | string;
  variant?: "light" | "filled" | "outline";
  size?: "xs" | "sm" | "md" | "lg";
}

export function DeliveryStatusBadge({
  status,
  variant = "light",
  size = "sm",
}: DeliveryStatusBadgeProps) {
  const { t } = useTranslation();
  return (
    <Badge color={COLOR_MAP[status] ?? "gray"} variant={variant} size={size}>
      {t(`delivery.status.${status}`, { defaultValue: status })}
    </Badge>
  );
}
