/**
 * AttendanceListPage — davomat yozuvlari jadvali.
 *
 * Ustunlar: xodim (user_id), kirish vaqti, chiqish vaqti, davomiylik, sana.
 * Filtrlar: sana (DateInput), xodim ID (TextInput — admin/accountant uchun).
 * RBAC:
 *   - administrator/accountant: istalgan xodim bo'yicha filtrlash.
 *   - agent/courier: faqat o'z yozuvlari (backend IDOR himoyasi).
 * i18n: uz/ru.
 */

import {
  Box,
  Button,
  Group,
  Loader,
  Pagination,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/auth/AuthContext";
import { useAttendanceList } from "@/api/attendanceApi";
import { usePagination } from "@/hooks/usePagination";
import { formatDuration } from "@/utils/date";
import type { AttendanceOut } from "./types";

// ─── Jadval qatori ───────────────────────────────────────────────────────────

function AttendanceRow({ record }: { record: AttendanceOut }) {
  const { t } = useTranslation();
  return (
    <Table.Tr>
      <Table.Td>
        <Text size="sm" ff="monospace" title={record.user_id}>
          {record.user_id.slice(0, 8)}…
        </Text>
      </Table.Td>
      <Table.Td>
        <Text size="sm">
          {new Date(record.work_date).toLocaleDateString()}
        </Text>
      </Table.Td>
      <Table.Td>
        <Text size="sm">
          {new Date(record.check_in_at).toLocaleTimeString()}
        </Text>
      </Table.Td>
      <Table.Td>
        <Text size="sm" c={record.check_out_at ? undefined : "dimmed"}>
          {record.check_out_at
            ? new Date(record.check_out_at).toLocaleTimeString()
            : "—"}
        </Text>
      </Table.Td>
      <Table.Td>
        <Text size="sm" c="dimmed">
          {formatDuration(record.check_in_at, record.check_out_at)}
        </Text>
      </Table.Td>
      <Table.Td>
        <Text size="sm" c="dimmed">
          {record.check_out_at
            ? t("attendance.status.present", {
                defaultValue: "Keldi",
              })
            : t("attendance.status.absent", {
                defaultValue: "Chiqmagan",
              })}
        </Text>
      </Table.Td>
    </Table.Tr>
  );
}

// ─── Asosiy komponent ─────────────────────────────────────────────────────────

export function AttendanceListPage() {
  const { t } = useTranslation();
  const { user } = useAuth();

  const isAdmin =
    user?.role === "administrator" || user?.role === "accountant";

  const { page, setPage, offset, pageSize, getTotalPages, resetPage } =
    usePagination(20);
  const [userIdFilter, setUserIdFilter] = useState("");
  const [dateFilter, setDateFilter]     = useState<Date | null>(null);

  // Sana ISO formatga (YYYY-MM-DD)
  const dateStr = dateFilter
    ? dateFilter.toISOString().slice(0, 10)
    : undefined;

  const { data, isLoading, isError, error } = useAttendanceList({
    user_id: isAdmin && userIdFilter.trim() ? userIdFilter.trim() : undefined,
    date:    dateStr,
    limit:   pageSize,
    offset,
  });

  const totalPages = getTotalPages(data?.total);

  const handleFilterChange = () => {
    resetPage();
  };

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Title order={3}>
          {t("attendance.title", { defaultValue: "Davomat" })}
        </Title>
      </Group>

      {/* Filtrlar */}
      <Group gap="sm" align="flex-end">
        {isAdmin && (
          <TextInput
            label={t("attendance.filter.user", {
              defaultValue: "Xodim bo'yicha",
            })}
            placeholder={t("attendance.filter.all_users", {
              defaultValue: "Barcha xodimlar",
            })}
            value={userIdFilter}
            onChange={(e) => setUserIdFilter(e.currentTarget.value)}
            onBlur={handleFilterChange}
            w={240}
            aria-label={t("attendance.filter.user", {
              defaultValue: "Xodim bo'yicha",
            })}
          />
        )}
        <DateInput
          label={t("attendance.filter.from", { defaultValue: "Sana" })}
          placeholder="YYYY-MM-DD"
          value={dateFilter}
          onChange={(v) => {
            setDateFilter(v);
            resetPage();
          }}
          clearable
          w={180}
        />
        {(userIdFilter || dateFilter) && (
          <Button
            variant="subtle"
            size="sm"
            onClick={() => {
              setUserIdFilter("");
              setDateFilter(null);
              resetPage();
            }}
          >
            {t("contracts.filter.clear", { defaultValue: "Tozalash" })}
          </Button>
        )}
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
            {error instanceof Error ? error.message : t("errors.unknown", { defaultValue: "Xato" })}
          </Text>
        </Box>
      ) : !data?.items.length ? (
        <Box py="xl" ta="center">
          <Text c="dimmed">
            {t("attendance.table.empty", {
              defaultValue: "Davomat yozuvlari topilmadi",
            })}
          </Text>
        </Box>
      ) : (
        <Table.ScrollContainer minWidth={750}>
          <Table striped highlightOnHover withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>
                  {t("attendance.table.employee", {
                    defaultValue: "Xodim",
                  })}
                </Table.Th>
                <Table.Th>
                  {t("attendance.table.date", { defaultValue: "Sana" })}
                </Table.Th>
                <Table.Th>
                  {t("attendance.table.check_in", {
                    defaultValue: "Kirish vaqti",
                  })}
                </Table.Th>
                <Table.Th>
                  {t("attendance.table.check_out", {
                    defaultValue: "Chiqish vaqti",
                  })}
                </Table.Th>
                <Table.Th>
                  {t("attendance.table.duration", {
                    defaultValue: "Davomiylik",
                  })}
                </Table.Th>
                <Table.Th>
                  {t("attendance.table.status", {
                    defaultValue: "Holat",
                  })}
                </Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.items.map((record) => (
                <AttendanceRow key={record.id} record={record} />
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}

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
    </Stack>
  );
}
