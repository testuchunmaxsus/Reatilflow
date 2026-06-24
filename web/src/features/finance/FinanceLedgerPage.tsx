/**
 * FinanceLedgerPage — buxgalteriya daftari sahifasi.
 *
 * Xususiyatlar:
 * - Paginated jadval (Mantine Table) — server-side
 * - Balans kartasi — tanlangan do'kon uchun
 * - "Yozuv qo'shish" modal — <Can permission="finance:create">
 * - "Tasdiqlash" tugmasi har bir qatorda — <Can permission="finance:approve">
 * - Filtrlar: entry_type (debit | credit)
 * - RBAC: <Can permission="finance:view"> — accountant, administrator ko'radi
 * - i18n uz/ru (defaultValue xavfsizlik uchun)
 *
 * RBAC:
 *   accountant / store  — finance:view
 *   accountant          — finance:create / finance:approve
 */

import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Card,
  Group,
  Loader,
  Modal,
  NumberInput,
  Pagination,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconCheck, IconPlus } from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Can } from "@/rbac/Can";
import { useApiError } from "@/hooks/useApiError";
import {
  useLedger,
  useBalance,
  useCreateLedgerEntry,
  useApproveLedgerEntry,
} from "./api/financeApi";
import type { LedgerFilters, LedgerEntryCreate } from "./types";

const PAGE_SIZE = 20;

// ─── Yordamchi: miqdor formatlash ─────────────────────────────────────────────

function formatAmount(amount: string, currency: string): string {
  const num = parseFloat(amount);
  if (isNaN(num)) return amount;
  return (
    num.toLocaleString("uz-UZ", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }) +
    " " +
    currency
  );
}

// ─── Yordamchi: sana formatlash ───────────────────────────────────────────────

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString("uz-UZ", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

// ─── Yozuv turi badge ─────────────────────────────────────────────────────────

function typeBadgeColor(type: string): string {
  return type === "credit" ? "green" : "red";
}

// ─── Yozuv qo'shish formasi ───────────────────────────────────────────────────

interface EntryFormValues {
  store_id: string;
  type: "debit" | "credit";
  amount: number | "";
  currency: string;
  ref_type: string;
}

interface AddEntryModalProps {
  opened: boolean;
  onClose: () => void;
}

function AddEntryModal({ opened, onClose }: AddEntryModalProps) {
  const { t } = useTranslation();
  const { showError } = useApiError();
  const createEntry = useCreateLedgerEntry();

  const form = useForm<EntryFormValues>({
    initialValues: {
      store_id: "",
      type: "debit",
      amount: "",
      currency: "UZS",
      ref_type: "",
    },
    validate: {
      store_id: (v) =>
        v.trim() === ""
          ? t("finance.form.store_id_required", {
              defaultValue: "Do'kon ID kiritilishi shart",
            })
          : null,
      amount: (v) =>
        v === "" || v <= 0
          ? t("finance.form.amount_positive", {
              defaultValue: "Miqdor noldan katta bo'lishi shart",
            })
          : null,
    },
  });

  const handleSubmit = async (values: EntryFormValues) => {
    if (values.amount === "") return;
    const payload: LedgerEntryCreate = {
      store_id: values.store_id.trim(),
      type: values.type,
      amount: String(values.amount),
      currency: values.currency || "UZS",
      ref_type: values.ref_type.trim() || null,
    };
    try {
      await createEntry.mutateAsync(payload);
      notifications.show({
        color: "green",
        message: t("finance.messages.created", {
          defaultValue: "Yozuv muvaffaqiyatli qo'shildi",
        }),
      });
      form.reset();
      onClose();
    } catch (err) {
      showError(err);
    }
  };

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={t("finance.modal.add_title", {
        defaultValue: "Yangi buxgalteriya yozuvi",
      })}
      size="md"
    >
      <form onSubmit={form.onSubmit((v) => { void handleSubmit(v); })}>
        <Stack gap="sm">
          <TextInput
            label={t("finance.form.store_id", { defaultValue: "Do'kon ID" })}
            placeholder="uuid"
            required
            {...form.getInputProps("store_id")}
          />
          <Select
            label={t("finance.form.type", { defaultValue: "Turi" })}
            data={[
              {
                value: "debit",
                label: t("finance.type.debit", { defaultValue: "Debet" }),
              },
              {
                value: "credit",
                label: t("finance.type.credit", { defaultValue: "Kredit" }),
              },
            ]}
            allowDeselect={false}
            {...form.getInputProps("type")}
          />
          <NumberInput
            label={t("finance.form.amount", { defaultValue: "Miqdor" })}
            placeholder="0.00"
            min={0.01}
            decimalScale={2}
            required
            {...form.getInputProps("amount")}
          />
          <TextInput
            label={t("finance.form.currency", { defaultValue: "Valyuta" })}
            placeholder="UZS"
            maxLength={3}
            {...form.getInputProps("currency")}
          />
          <TextInput
            label={t("finance.form.ref_type", {
              defaultValue: "Havola turi (ixtiyoriy)",
            })}
            placeholder="order, invoice ..."
            {...form.getInputProps("ref_type")}
          />
          <Group justify="flex-end" mt="sm">
            <Button variant="subtle" onClick={onClose}>
              {t("common.cancel", { defaultValue: "Bekor qilish" })}
            </Button>
            <Button type="submit" loading={createEntry.isPending}>
              {t("common.save", { defaultValue: "Saqlash" })}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}

// ─── Asosiy sahifa ────────────────────────────────────────────────────────────

export function FinanceLedgerPage() {
  const { t } = useTranslation();
  const { showError } = useApiError();

  // Filtrlar
  const [typeFilter, setTypeFilter] = useState<"debit" | "credit" | "">("");
  const [page, setPage] = useState(1);
  const offset = (page - 1) * PAGE_SIZE;

  // Balans uchun store_id (ixtiyoriy filtr)
  const [balanceStoreId, setBalanceStoreId] = useState("");

  // Modal
  const [addOpened, { open: openAdd, close: closeAdd }] =
    useDisclosure(false);

  const filters: LedgerFilters = {
    ...(typeFilter ? { entry_type: typeFilter } : {}),
    limit: PAGE_SIZE,
    offset,
  };

  const { data, isLoading, isError, error } = useLedger(filters);
  const balanceQuery = useBalance(balanceStoreId, !!balanceStoreId);
  const approveEntry = useApproveLedgerEntry();

  const handleApprove = async (entryId: string) => {
    try {
      await approveEntry.mutateAsync(entryId);
      notifications.show({
        color: "teal",
        message: t("finance.messages.approved", {
          defaultValue: "Yozuv tasdiqlandi",
        }),
      });
    } catch (err) {
      showError(err);
    }
  };

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1;

  const typeFilterOptions = [
    {
      value: "",
      label: t("finance.filter.all_types", {
        defaultValue: "Barcha turlar",
      }),
    },
    {
      value: "debit",
      label: t("finance.type.debit", { defaultValue: "Debet" }),
    },
    {
      value: "credit",
      label: t("finance.type.credit", { defaultValue: "Kredit" }),
    },
  ];

  return (
    <Can
      permission="finance:view"
      fallback={
        <Box py="xl" ta="center">
          <Text c="dimmed">
            {t("finance.access_denied", {
              defaultValue:
                "Bu sahifani ko'rish uchun ruxsat yo'q",
            })}
          </Text>
        </Box>
      }
    >
      <Stack gap="md">
        {/* Sarlavha va qo'shish tugmasi */}
        <Group justify="space-between">
          <Title order={3}>
            {t("pages.finance.title", { defaultValue: "Buxgalteriya daftari" })}
          </Title>
          <Can permission="finance:create">
            <Button leftSection={<IconPlus size={16} />} onClick={openAdd}>
              {t("finance.actions.add_entry", {
                defaultValue: "Yozuv qo'shish",
              })}
            </Button>
          </Can>
        </Group>

        {/* Balans kartasi */}
        <Card withBorder radius="md" p="md">
          <Stack gap="xs">
            <Text fw={600} size="sm">
              {t("finance.balance.title", { defaultValue: "Do'kon balansi" })}
            </Text>
            <Group gap="sm" align="flex-end">
              <TextInput
                size="xs"
                placeholder={t("finance.balance.store_id_placeholder", {
                  defaultValue: "Do'kon ID kiriting...",
                })}
                value={balanceStoreId}
                onChange={(e) => setBalanceStoreId(e.currentTarget.value)}
                w={280}
                aria-label={t("finance.balance.store_id_placeholder", {
                  defaultValue: "Do'kon ID kiriting...",
                })}
              />
              {balanceQuery.isLoading && <Loader size="xs" />}
              {balanceQuery.data && (
                <Text fw={700} size="lg" c="blue">
                  {formatAmount(
                    balanceQuery.data.balance,
                    balanceQuery.data.currency,
                  )}
                </Text>
              )}
              {balanceQuery.isError && (
                <Text size="sm" c="red">
                  {t("finance.balance.error", {
                    defaultValue: "Balans topilmadi",
                  })}
                </Text>
              )}
            </Group>
          </Stack>
        </Card>

        {/* Filtrlar */}
        <Group gap="sm" wrap="wrap">
          <Select
            data={typeFilterOptions}
            value={typeFilter}
            onChange={(v) => {
              setTypeFilter((v ?? "") as "debit" | "credit" | "");
              setPage(1);
            }}
            w={180}
            aria-label={t("finance.filter.type", { defaultValue: "Tur filtri" })}
            allowDeselect={false}
          />
          {typeFilter && (
            <Button
              variant="subtle"
              size="sm"
              onClick={() => {
                setTypeFilter("");
                setPage(1);
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
              {error instanceof Error
                ? error.message
                : t("errors.unknown", { defaultValue: "Xato yuz berdi" })}
            </Text>
          </Box>
        ) : !data?.items.length ? (
          <Box py="xl" ta="center">
            <Text c="dimmed">
              {t("finance.table.empty", {
                defaultValue: "Yozuvlar topilmadi",
              })}
            </Text>
          </Box>
        ) : (
          <Table.ScrollContainer minWidth={900}>
            <Table striped highlightOnHover withTableBorder>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>
                    {t("finance.table.type", { defaultValue: "Turi" })}
                  </Table.Th>
                  <Table.Th>
                    {t("finance.table.amount", { defaultValue: "Miqdor" })}
                  </Table.Th>
                  <Table.Th>
                    {t("finance.table.store_id", { defaultValue: "Do'kon" })}
                  </Table.Th>
                  <Table.Th>
                    {t("finance.table.ref_type", {
                      defaultValue: "Havola turi",
                    })}
                  </Table.Th>
                  <Table.Th>
                    {t("finance.table.entry_date", { defaultValue: "Sana" })}
                  </Table.Th>
                  <Table.Th>
                    {t("catalog.table.actions", {
                      defaultValue: "Amallar",
                    })}
                  </Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {data.items.map((entry) => (
                  <Table.Tr key={entry.id}>
                    <Table.Td>
                      <Badge
                        color={typeBadgeColor(entry.type)}
                        variant="light"
                        size="sm"
                      >
                        {t(`finance.type.${entry.type}`, {
                          defaultValue:
                            entry.type === "credit" ? "Kredit" : "Debet",
                        })}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Text
                        size="sm"
                        fw={600}
                        c={entry.type === "credit" ? "green" : "red"}
                      >
                        {formatAmount(entry.amount, entry.currency)}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" ff="monospace" c="dimmed" lineClamp={1}>
                        {entry.store_id}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" c="dimmed">
                        {entry.ref_type ?? "—"}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">{formatDate(entry.entry_date)}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Can permission="finance:approve">
                        <Tooltip
                          label={t("finance.actions.approve", {
                            defaultValue: "Tasdiqlash",
                          })}
                        >
                          <ActionIcon
                            variant="subtle"
                            color="teal"
                            onClick={() => { void handleApprove(entry.id); }}
                            loading={
                              approveEntry.isPending &&
                              approveEntry.variables === entry.id
                            }
                            aria-label={t("finance.actions.approve", {
                              defaultValue: "Tasdiqlash",
                            })}
                          >
                            <IconCheck size={16} />
                          </ActionIcon>
                        </Tooltip>
                      </Can>
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

        {/* Yozuv qo'shish modal */}
        <AddEntryModal opened={addOpened} onClose={closeAdd} />
      </Stack>
    </Can>
  );
}
