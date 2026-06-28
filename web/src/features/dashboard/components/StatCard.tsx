/**
 * StatCard — umumiy KPI karta komponenti.
 * DashboardPage'dan ajratildi, barcha rol-dashboard'lar uchun umumiy.
 */

import { Card, Group, Loader, Text, ThemeIcon } from "@mantine/core";

// ─── Raqamni formatlash yordamchisi ─────────────────────────────────────────

export function formatAmount(value: string | number): string {
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) return String(value);
  return new Intl.NumberFormat("uz-UZ").format(Math.round(num));
}

// ─── StatCard ────────────────────────────────────────────────────────────────

export interface StatCardProps {
  icon: React.ReactNode;
  color: string;
  label: string;
  value: string | number | undefined;
  sub?: string;
  loading?: boolean;
  error?: string | null;
}

export function StatCard({
  icon,
  color,
  label,
  value,
  sub,
  loading,
  error,
}: StatCardProps) {
  return (
    <Card shadow="sm" padding="lg" radius="md" withBorder h="100%">
      <Group gap="sm" mb="xs">
        <ThemeIcon size={36} radius="md" color={color} variant="light">
          {icon}
        </ThemeIcon>
        <Text fw={500} size="sm" c="dimmed">
          {label}
        </Text>
      </Group>

      {loading ? (
        <Group gap="xs" mt={4}>
          <Loader size="xs" />
          <Text size="sm" c="dimmed">...</Text>
        </Group>
      ) : error ? (
        <Text size="sm" c="red" mt={4}>
          {error}
        </Text>
      ) : (
        <>
          <Text fw={700} size="xl" mt={4}>
            {value ?? "—"}
          </Text>
          {sub && (
            <Text size="xs" c="dimmed" mt={2}>
              {sub}
            </Text>
          )}
        </>
      )}
    </Card>
  );
}
