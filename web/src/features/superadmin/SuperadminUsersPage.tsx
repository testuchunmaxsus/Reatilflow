/**
 * SuperadminUsersPage — cross-tenant foydalanuvchilar sahifasi.
 *
 * Xususiyatlar:
 * - Barcha korxonalar bo'yicha foydalanuvchilar
 * - Korxona bo'yicha filter (Select)
 * - Rol bo'yicha filter
 * - Telefon maskPhone bilan
 * - Paginated (20 ta/sahifa)
 * - i18n uz/ru
 *
 * Ma'lumot: GET /superadmin/users?enterprise_id=&role=&limit=&offset=
 */

import {
  Badge,
  Box,
  Group,
  Loader,
  Pagination,
  Select,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useSuperadminUsers, useEnterprises } from "./api/superadminApi";
import { formatDate } from "@/utils/date";

const PAGE_SIZE = 20;

// ─── Rol rangi ────────────────────────────────────────────────────────────────

function roleBadgeColor(role: string): string {
  switch (role) {
    case "administrator":
      return "red";
    case "agent":
      return "blue";
    case "courier":
      return "teal";
    case "accountant":
      return "violet";
    case "store":
      return "orange";
    default:
      return "gray";
  }
}

// ─── Telefon maskalash ────────────────────────────────────────────────────────

function maskPhone(phone: string): string {
  if (phone.length <= 4) return phone;
  return phone.slice(0, -4).replace(/\d/g, "*") + phone.slice(-4);
}

// ─── Komponent ────────────────────────────────────────────────────────────────

export function SuperadminUsersPage() {
  const { t } = useTranslation();

  const [page, setPage] = useState(1);
  const [enterpriseFilter, setEnterpriseFilter] = useState<string>("");
  const [roleFilter, setRoleFilter] = useState<string>("");

  const offset = (page - 1) * PAGE_SIZE;

  // Korxonalar ro'yxati (filter Select uchun)
  const { data: enterprisesData } = useEnterprises({ limit: 200, offset: 0 });

  const { data, isLoading, isError, error } = useSuperadminUsers({
    enterprise_id: enterpriseFilter,
    role: roleFilter,
    limit: PAGE_SIZE,
    offset,
  });

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1;

  const handleEnterpriseChange = useCallback((val: string | null) => {
    setEnterpriseFilter(val ?? "");
    setPage(1);
  }, []);

  const handleRoleChange = useCallback((val: string | null) => {
    setRoleFilter(val ?? "");
    setPage(1);
  }, []);

  const enterpriseOptions = (enterprisesData?.items ?? []).map((ent) => ({
    value: ent.id,
    label: ent.name,
  }));

  const roleOptions = [
    { value: "administrator", label: t("common.role.administrator") },
    { value: "agent", label: t("common.role.agent") },
    { value: "courier", label: t("common.role.courier") },
    { value: "accountant", label: t("common.role.accountant") },
    { value: "store", label: t("common.role.store") },
  ];

  return (
    <Stack gap="md">
      <Title order={3}>{t("nav.users")}</Title>

      {/* Filtrlar */}
      <Group gap="sm">
        <Select
          placeholder={t("superadmin.users.all_enterprises")}
          value={enterpriseFilter || null}
          onChange={handleEnterpriseChange}
          data={enterpriseOptions}
          clearable
          searchable
          w={240}
          aria-label={t("superadmin.users.enterprise_filter")}
        />
        <Select
          placeholder={t("users.filter.all_roles")}
          value={roleFilter || null}
          onChange={handleRoleChange}
          data={roleOptions}
          clearable
          w={180}
          aria-label={t("users.filter.role")}
        />
      </Group>

      {/* Jadval */}
      {isLoading ? (
        <Group justify="center" py="xl">
          <Loader />
          <Text c="dimmed">{t("common.loading")}</Text>
        </Group>
      ) : isError ? (
        <Box py="xl" ta="center">
          <Text c="red">
            {error instanceof Error ? error.message : t("errors.unknown")}
          </Text>
        </Box>
      ) : !data?.items.length ? (
        <Box py="xl" ta="center">
          <Text c="dimmed">{t("users.table.empty")}</Text>
        </Box>
      ) : (
        <Table.ScrollContainer minWidth={900}>
          <Table striped highlightOnHover withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t("users.table.full_name")}</Table.Th>
                <Table.Th>{t("users.table.phone")}</Table.Th>
                <Table.Th>{t("users.table.role")}</Table.Th>
                <Table.Th>{t("users.table.status")}</Table.Th>
                <Table.Th>{t("superadmin.users.enterprise_column")}</Table.Th>
                <Table.Th>{t("superadmin.table.created_at")}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.items.map((user) => (
                <Table.Tr key={user.id}>
                  <Table.Td>
                    <Text size="sm" fw={500}>{user.full_name}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed">{maskPhone(user.phone)}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Badge color={roleBadgeColor(user.role)} variant="light" size="sm">
                      {t(`common.role.${user.role}`, { defaultValue: user.role })}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Badge
                      color={user.is_active ? "green" : "gray"}
                      variant="dot"
                      size="sm"
                    >
                      {user.is_active
                        ? t("users.status.active")
                        : t("users.status.inactive")}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed">{user.enterprise_name ?? "—"}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed">{formatDate(user.created_at)}</Text>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}

      {/* Pagination */}
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
