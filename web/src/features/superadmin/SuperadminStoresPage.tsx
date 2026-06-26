/**
 * SuperadminStoresPage — platforma do'konlar boshqaruv sahifasi.
 *
 * Xususiyatlar:
 * - Jadval: nom, egasi, telefon, manzil, "Platforma" badge, yaratilgan sana
 * - "Platforma do'kon qo'shish" tugmasi → SuperadminStoreFormModal
 * - POST /superadmin/stores → yangilanish
 * - Pagination (20 ta/sahifa)
 * - i18n uz/ru inline defaultValue bilan
 */

import {
  Badge,
  Box,
  Button,
  Group,
  Loader,
  Pagination,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { IconPlus } from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useDisclosure } from "@mantine/hooks";
import { useSuperadminStores } from "./api/superadminApi";
import { SuperadminStoreFormModal } from "./components/SuperadminStoreFormModal";
import { formatDate } from "@/utils/date";

const PAGE_SIZE = 20;

// ─── Komponent ────────────────────────────────────────────────────────────────

export function SuperadminStoresPage() {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const [formOpened, { open: openForm, close: closeForm }] = useDisclosure(false);

  const offset = (page - 1) * PAGE_SIZE;

  const { data, isLoading, isError, error } = useSuperadminStores({
    limit: PAGE_SIZE,
    offset,
  });

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1;
  const items = data?.items ?? [];

  return (
    <Stack gap="md">
      {/* Sarlavha */}
      <Group justify="space-between">
        <Title order={3}>
          {t("superadmin.stores.title", { defaultValue: "Platforma do'konlar" })}
        </Title>
        <Button leftSection={<IconPlus size={16} />} onClick={openForm}>
          {t("superadmin.stores.actions.create", {
            defaultValue: "Platforma do'kon qo'shish",
          })}
        </Button>
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
      ) : !items.length ? (
        <Box py="xl" ta="center">
          <Text c="dimmed">
            {t("superadmin.stores.table.empty", {
              defaultValue: "Platforma do'konlar topilmadi",
            })}
          </Text>
        </Box>
      ) : (
        <Table.ScrollContainer minWidth={760}>
          <Table striped highlightOnHover withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>
                  {t("superadmin.stores.table.name", { defaultValue: "Nomi" })}
                </Table.Th>
                <Table.Th>
                  {t("superadmin.stores.table.owner_name", {
                    defaultValue: "Egasi",
                  })}
                </Table.Th>
                <Table.Th>
                  {t("superadmin.stores.table.phone", {
                    defaultValue: "Telefon",
                  })}
                </Table.Th>
                <Table.Th>
                  {t("superadmin.stores.table.address", {
                    defaultValue: "Manzil",
                  })}
                </Table.Th>
                <Table.Th>
                  {t("superadmin.stores.table.type", {
                    defaultValue: "Tur",
                  })}
                </Table.Th>
                <Table.Th>
                  {t("superadmin.stores.table.created_at", {
                    defaultValue: "Yaratilgan",
                  })}
                </Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {items.map((store) => (
                <Table.Tr key={store.id}>
                  <Table.Td>
                    <Text size="sm" fw={500}>
                      {store.name}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed">
                      {store.owner_name ?? "—"}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed">
                      {store.phone ?? "—"}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed" lineClamp={1}>
                      {store.address ?? "—"}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    {store.is_platform_managed ? (
                      <Badge color="violet" variant="light" size="sm">
                        {t("superadmin.stores.badge.platform", {
                          defaultValue: "Platforma",
                        })}
                      </Badge>
                    ) : (
                      <Badge color="gray" variant="light" size="sm">
                        {t("superadmin.stores.badge.tenant", {
                          defaultValue: "Tenant",
                        })}
                      </Badge>
                    )}
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed">
                      {formatDate(store.created_at)}
                    </Text>
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

      {/* Modal */}
      <SuperadminStoreFormModal opened={formOpened} onClose={closeForm} />
    </Stack>
  );
}
