/**
 * ImportPage — Excel fayl yoki Nakladnoy rasm import sahifasi.
 *
 * Oqim (ADR-010 Variant C — stateless parse + client-held preview):
 * 1. Foydalanuvchi fayl tanlaydi (xlsx yoki rasm)
 * 2. POST /import/excel/parse yoki /import/nakladnoy/parse → ParsedRow[]
 * 3. Preview jadval tahrirlanadi (ImportPreviewTable)
 * 4. "Tasdiqlab import" → POST /import/confirm → natija
 *
 * RBAC: "import:create" ruxsati tekshiriladi.
 * Idempotentlik: har preview satriga crypto.randomUUID() client_uuid.
 */

import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Divider,
  Group,
  Loader,
  Stack,
  Tabs,
  Text,
  Title,
} from "@mantine/core";
import {
  IconAlertCircle,
  IconCheck,
  IconFileSpreadsheet,
  IconPhoto,
  IconUpload,
} from "@tabler/icons-react";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { notifications } from "@mantine/notifications";
import { Can } from "@/rbac/Can";
import {
  useParseExcel,
  useParseNakladnoy,
  useImportConfirm,
  type ImportSource,
} from "@/api/import";
import { useApiError } from "@/hooks/useApiError";
import { ImportPreviewTable, type EditableRow } from "./ImportPreviewTable";
import type { ParsedRow } from "@/api/import";

// ─── Yordamchi: ParsedRow → EditableRow (client_uuid qo'shish) ───────────────

function toEditableRows(rows: ParsedRow[]): EditableRow[] {
  return rows.map((r) => ({
    ...r,
    client_uuid: crypto.randomUUID(),
  }));
}

// ─── Fayl tanlash tugmasi ─────────────────────────────────────────────────────

interface FilePickerProps {
  accept: string;
  label: string;
  hint: string;
  loading: boolean;
  onFile: (file: File) => void;
}

function FilePicker({ accept, label, hint, loading, onFile }: FilePickerProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <Stack gap="xs" align="center" py="lg">
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        style={{ display: "none" }}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
          // inputni tozala — bir xil faylni qayta yuklash uchun
          if (inputRef.current) inputRef.current.value = "";
        }}
      />
      <Button
        leftSection={<IconUpload size={16} />}
        loading={loading}
        onClick={() => inputRef.current?.click()}
        variant="light"
        size="md"
      >
        {label}
      </Button>
      <Text size="xs" c="dimmed" ta="center">
        {hint}
      </Text>
    </Stack>
  );
}

// ─── Asosiy kontent ───────────────────────────────────────────────────────────

function ImportContent() {
  const { t } = useTranslation();
  const { showError } = useApiError();

  const [activeTab, setActiveTab] = useState<string | null>("excel");
  const [previewRows, setPreviewRows] = useState<EditableRow[]>([]);
  const [activeSource, setActiveSource] = useState<ImportSource>("excel");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [visionEnabled, setVisionEnabled] = useState<boolean | null>(null);
  const [confirmResult, setConfirmResult] = useState<{
    created: number;
    skipped: number;
    errors: { row_index: number; code: string; message: string }[];
    target: "catalog" | "store_inventory";
  } | null>(null);

  const parseExcel = useParseExcel();
  const parseNakladnoy = useParseNakladnoy();
  const confirmImport = useImportConfirm();

  // ─── Excel yuklash ──────────────────────────────────────────────────────────

  const handleExcelFile = async (file: File) => {
    setConfirmResult(null);
    setWarnings([]);
    setPreviewRows([]);
    setActiveSource("excel");

    // UI darajasi validatsiya: faqat .xlsx (MIME yoki kengaytma)
    const isXlsx =
      file.name.toLowerCase().endsWith(".xlsx") ||
      file.type ===
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
    if (!isXlsx) {
      notifications.show({
        color: "red",
        title: t("import.errors.invalid_file", { defaultValue: "Noto'g'ri fayl" }),
        message: t("import.errors.xlsx_only", {
          defaultValue: "Faqat .xlsx fayl qabul qilinadi",
        }),
      });
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      notifications.show({
        color: "red",
        title: t("import.errors.too_large", { defaultValue: "Fayl juda katta" }),
        message: t("import.errors.max_5mb", { defaultValue: "Maksimal hajm 5 MB" }),
      });
      return;
    }

    try {
      const result = await parseExcel.mutateAsync(file);
      setPreviewRows(toEditableRows(result.rows));
      setWarnings(result.warnings ?? []);
    } catch (err) {
      showError(err);
    }
  };

  // ─── Rasm yuklash ───────────────────────────────────────────────────────────

  const handleImageFile = async (file: File) => {
    setConfirmResult(null);
    setWarnings([]);
    setPreviewRows([]);
    setActiveSource("nakladnoy");
    setVisionEnabled(null);

    const ALLOWED = ["image/jpeg", "image/png", "image/webp"];
    if (!ALLOWED.includes(file.type)) {
      notifications.show({
        color: "red",
        title: t("import.errors.invalid_file", { defaultValue: "Noto'g'ri fayl" }),
        message: t("import.errors.image_formats", {
          defaultValue: "Faqat JPEG, PNG, WebP qabul qilinadi",
        }),
      });
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      notifications.show({
        color: "red",
        title: t("import.errors.too_large", { defaultValue: "Fayl juda katta" }),
        message: t("import.errors.max_8mb", { defaultValue: "Maksimal hajm 8 MB" }),
      });
      return;
    }

    try {
      const result = await parseNakladnoy.mutateAsync(file);
      setVisionEnabled(result.vision_enabled);
      setPreviewRows(toEditableRows(result.rows));
      setWarnings(result.warnings ?? []);
    } catch (err) {
      showError(err);
    }
  };

  // ─── Import tasdiqlash ──────────────────────────────────────────────────────

  const handleConfirm = async () => {
    // Satrlar validatsiyasi
    const invalidRows = previewRows.filter(
      (r) => !r.name.trim() || r.qty <= 0,
    );
    if (invalidRows.length > 0) {
      notifications.show({
        color: "orange",
        title: t("import.errors.invalid_rows_title", {
          defaultValue: "Noto'g'ri satrlar",
        }),
        message: t("import.errors.invalid_rows_msg", {
          defaultValue:
            "Ba'zi satrlarda nom bo'sh yoki miqdor 0. Iltimos tekshiring.",
        }),
      });
      return;
    }
    if (previewRows.length === 0) return;

    setConfirmResult(null);
    try {
      const result = await confirmImport.mutateAsync({
        source: activeSource,
        rows: previewRows.map((r) => ({
          name: r.name,
          sku: r.sku ?? undefined,
          barcode: r.barcode ?? undefined,
          qty: r.qty,
          price: r.price,
          currency: r.currency,
          expiry_date: r.expiry_date ?? undefined,
          client_uuid: r.client_uuid,
        })),
      });
      setConfirmResult(result);
      // Muvaffaqiyatli import — preview ni tozala
      if (result.errors.length === 0) {
        setPreviewRows([]);
      }
      notifications.show({
        color: result.errors.length > 0 ? "yellow" : "green",
        title: t("import.messages.confirm_done", {
          defaultValue: "Import yakunlandi",
        }),
        message: t("import.messages.confirm_detail", {
          defaultValue:
            "Yaratildi: {{created}}, o'tkazib yuborildi: {{skipped}}, xato: {{errors}}",
          created: result.created,
          skipped: result.skipped,
          errors: result.errors.length,
        }),
      });
    } catch (err) {
      showError(err);
    }
  };

  const isParsing = parseExcel.isPending || parseNakladnoy.isPending;
  const isConfirming = confirmImport.isPending;

  return (
    <Stack gap="lg">
      <Title order={3}>
        {t("import.title", { defaultValue: "Import (Excel / Nakladnoy rasm)" })}
      </Title>

      {/* ─── Fayl yuklash ─── */}
      <Card withBorder padding="md" radius="sm">
        <Tabs value={activeTab} onChange={setActiveTab}>
          <Tabs.List>
            <Tabs.Tab
              value="excel"
              leftSection={<IconFileSpreadsheet size={16} />}
            >
              {t("import.tabs.excel", { defaultValue: "Excel (.xlsx)" })}
            </Tabs.Tab>
            <Tabs.Tab value="image" leftSection={<IconPhoto size={16} />}>
              {t("import.tabs.nakladnoy", { defaultValue: "Nakladnoy rasmi" })}
            </Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="excel" pt="xs">
            {isParsing && activeSource === "excel" ? (
              <Group justify="center" py="lg">
                <Loader size="sm" />
                <Text c="dimmed">
                  {t("import.parsing", { defaultValue: "Fayl tahlil qilinmoqda..." })}
                </Text>
              </Group>
            ) : (
              <FilePicker
                accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                label={t("import.actions.choose_excel", {
                  defaultValue: "Excel fayl tanlash",
                })}
                hint={t("import.hints.excel", {
                  defaultValue: "Faqat .xlsx, maksimal 5 MB. Sarlavha qatori majburiy.",
                })}
                loading={parseExcel.isPending}
                onFile={(f) => {
                  void handleExcelFile(f);
                }}
              />
            )}
          </Tabs.Panel>

          <Tabs.Panel value="image" pt="xs">
            {isParsing && activeSource === "nakladnoy" ? (
              <Group justify="center" py="lg">
                <Loader size="sm" />
                <Text c="dimmed">
                  {t("import.parsing_image", {
                    defaultValue: "Rasm o'qilmoqda (AI Vision)...",
                  })}
                </Text>
              </Group>
            ) : (
              <FilePicker
                accept="image/jpeg,image/png,image/webp"
                label={t("import.actions.choose_image", {
                  defaultValue: "Nakladnoy rasmi tanlash",
                })}
                hint={t("import.hints.image", {
                  defaultValue:
                    "JPEG, PNG, WebP, maksimal 8 MB. AI rasm o'qiydi — natijani tekshiring.",
                })}
                loading={parseNakladnoy.isPending}
                onFile={(f) => {
                  void handleImageFile(f);
                }}
              />
            )}

            {/* Vision xabari */}
            {visionEnabled === false && (
              <Alert
                icon={<IconAlertCircle size={16} />}
                color="orange"
                mt="xs"
              >
                {t("import.errors.vision_unavailable", {
                  defaultValue:
                    "Rasm o'qib bo'lmadi. Qo'lda kiriting yoki Excel ishlating.",
                })}
              </Alert>
            )}
          </Tabs.Panel>
        </Tabs>
      </Card>

      {/* ─── Ogohlantirishlar ─── */}
      {warnings.length > 0 && (
        <Alert icon={<IconAlertCircle size={16} />} color="yellow">
          <Stack gap={2}>
            {warnings.map((w, i) => (
              <Text key={i} size="sm">
                {w}
              </Text>
            ))}
          </Stack>
        </Alert>
      )}

      {/* ─── Preview jadval ─── */}
      {previewRows.length > 0 && (
        <>
          <Divider
            label={t("import.sections.preview", {
              defaultValue: "Preview ({{count}} satr) — tahrirlang, so'ng tasdiqlang",
              count: previewRows.length,
            })}
            labelPosition="left"
          />
          <ImportPreviewTable rows={previewRows} onChange={setPreviewRows} />

          <Group justify="flex-end">
            <Button
              variant="subtle"
              onClick={() => {
                setPreviewRows([]);
                setConfirmResult(null);
                setWarnings([]);
              }}
              disabled={isConfirming}
            >
              {t("common.cancel")}
            </Button>
            <Button
              leftSection={<IconCheck size={16} />}
              onClick={() => {
                void handleConfirm();
              }}
              loading={isConfirming}
              disabled={previewRows.length === 0}
            >
              {t("import.actions.confirm", {
                defaultValue: "Tasdiqlab import ({count})",
                count: previewRows.length,
              })}
            </Button>
          </Group>
        </>
      )}

      {/* ─── Natija ─── */}
      {confirmResult && (
        <>
          <Divider
            label={t("import.sections.result", { defaultValue: "Import natijasi" })}
            labelPosition="left"
          />
          <Card withBorder padding="md">
            <Group gap="sm" wrap="wrap">
              <Badge color="green" variant="light">
                {t("import.result.created", {
                  defaultValue: "Yaratildi: {{n}}",
                  n: confirmResult.created,
                })}
              </Badge>
              <Badge color="gray" variant="light">
                {t("import.result.skipped", {
                  defaultValue: "O'tkazildi: {{n}}",
                  n: confirmResult.skipped,
                })}
              </Badge>
              {confirmResult.errors.length > 0 && (
                <Badge color="red" variant="light">
                  {t("import.result.errors", {
                    defaultValue: "Xato: {{n}}",
                    n: confirmResult.errors.length,
                  })}
                </Badge>
              )}
              <Badge color="blue" variant="light">
                {t("import.result.target", {
                  defaultValue: "Maqsad: {{t}}",
                  t: confirmResult.target === "catalog" ? "Katalog" : "Do'kon ombori",
                })}
              </Badge>
            </Group>

            {confirmResult.errors.length > 0 && (
              <Box mt="sm">
                <Text size="sm" fw={500} mb={4}>
                  {t("import.result.error_list", { defaultValue: "Xatoliklar:" })}
                </Text>
                {confirmResult.errors.map((e, i) => (
                  <Text key={i} size="xs" c="red">
                    Satr {e.row_index}: [{e.code}] {e.message}
                  </Text>
                ))}
              </Box>
            )}
          </Card>
        </>
      )}
    </Stack>
  );
}

// ─── Sahifa (RBAC wrapper) ─────────────────────────────────────────────────────

export function ImportPage() {
  const { t } = useTranslation();

  return (
    <Can
      permission="import:create"
      fallback={
        <Box py="xl" ta="center">
          <Text c="dimmed">
            {t("import.access_denied", {
              defaultValue: "Bu sahifani ko'rish uchun ruxsat yo'q",
            })}
          </Text>
        </Box>
      }
    >
      <ImportContent />
    </Can>
  );
}
