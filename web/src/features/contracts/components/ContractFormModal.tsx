/**
 * ContractFormModal — shartnoma yaratish / tahrirlash modal.
 *
 * Yaratish: store_id, number, valid_from, valid_to, contract_type, branch_id.
 * Tahrirlash: number, valid_from, valid_to, contract_type, branch_id (version lock).
 * Status DERIVED — faqat ko'rsatiladi, klient o'zgartira olmaydi.
 * RBAC: administrator / accountant (backend ham tekshiradi).
 * i18n uz/ru.
 */

import {
  Button,
  Group,
  Modal,
  Select,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useForm } from "@mantine/form";
import { useTranslation } from "react-i18next";
import { useCreateContract, useUpdateContract } from "../api/contractsApi";
import { useApiError } from "@/hooks/useApiError";
import { toLocalYMD, parseYMD } from "@/utils/date";
import type { ContractOut } from "../types";

// ─── Props ────────────────────────────────────────────────────────────────────

interface ContractFormModalProps {
  opened: boolean;
  onClose: () => void;
  contract?: ContractOut;
}

// ─── Forma qiymatlari ─────────────────────────────────────────────────────────

interface ContractFormValues {
  store_id: string;
  number: string;
  /** YYYY-MM-DD string */
  valid_from: string;
  /** YYYY-MM-DD string */
  valid_to: string;
  contract_type: string;
  branch_id: string;
}

// ─── Shartnoma turlari ────────────────────────────────────────────────────────

const CONTRACT_TYPES = ["trade", "employment", "service", "other"] as const;

// ─── Sana validatsiya yordamchisi ─────────────────────────────────────────────

function isValidDate(s: string): boolean {
  if (!s) return false;
  const re = /^\d{4}-\d{2}-\d{2}$/;
  if (!re.test(s)) return false;
  const d = new Date(s);
  return !isNaN(d.getTime());
}

// ─── Komponent ────────────────────────────────────────────────────────────────

export function ContractFormModal({
  opened,
  onClose,
  contract,
}: ContractFormModalProps) {
  const { t } = useTranslation();
  const { showError, showSuccess } = useApiError();
  const isEdit = Boolean(contract);

  const createContract = useCreateContract();
  const updateContract = useUpdateContract();

  const contractTypeOptions = [
    { value: "", label: t("contracts.form.type_any") },
    ...CONTRACT_TYPES.map((ct) => ({
      value: ct,
      label: t(`contracts.type.${ct}`),
    })),
  ];

  const form = useForm<ContractFormValues>({
    initialValues: {
      store_id: contract?.store_id ?? "",
      number: contract?.number ?? "",
      valid_from: contract?.valid_from ?? "",
      valid_to: contract?.valid_to ?? "",
      contract_type: contract?.contract_type ?? "",
      branch_id: contract?.branch_id ?? "",
    },
    validate: {
      store_id: (v) =>
        !isEdit && !v.trim()
          ? t("contracts.form.store_id_required")
          : null,
      number: (v) =>
        !v.trim() ? t("contracts.form.number_required") : null,
      valid_from: (v) =>
        !isValidDate(v) ? t("contracts.form.valid_from_required") : null,
      valid_to: (v, values) => {
        if (!isValidDate(v)) return t("contracts.form.valid_to_required");
        if (values.valid_from && v < values.valid_from)
          return t("contracts.form.valid_to_before_from");
        return null;
      },
    },
  });

  const handleClose = () => {
    form.reset();
    onClose();
  };

  const handleSubmit = async (values: ContractFormValues) => {
    try {
      if (isEdit && contract) {
        await updateContract.mutateAsync({
          id: contract.id,
          data: {
            number: values.number,
            valid_from: values.valid_from,
            valid_to: values.valid_to,
            contract_type: values.contract_type || null,
            branch_id: values.branch_id || null,
            version: contract.version,
          },
        });
        showSuccess("contracts.messages.updated");
      } else {
        await createContract.mutateAsync({
          store_id: values.store_id,
          number: values.number,
          valid_from: values.valid_from,
          valid_to: values.valid_to,
          contract_type: values.contract_type || null,
          branch_id: values.branch_id || null,
        });
        showSuccess("contracts.messages.created");
      }
      handleClose();
    } catch (err) {
      showError(err);
    }
  };

  const isPending = createContract.isPending || updateContract.isPending;

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={
        <Text fw={600}>
          {isEdit
            ? t("contracts.form.edit_title")
            : t("contracts.form.create_title")}
        </Text>
      }
      size="md"
      centered
    >
      <form onSubmit={form.onSubmit((v) => { void handleSubmit(v); })}>
        <Stack gap="sm">
          {!isEdit && (
            <TextInput
              label={t("contracts.form.store_id")}
              placeholder="UUID"
              description={t("contracts.form.store_id_hint")}
              required
              {...form.getInputProps("store_id")}
            />
          )}

          <TextInput
            label={t("contracts.form.number")}
            placeholder={t("contracts.form.number_placeholder")}
            required
            {...form.getInputProps("number")}
          />

          <Group grow>
            <DateInput
              label={t("contracts.form.valid_from")}
              placeholder="2026-01-01"
              valueFormat="YYYY-MM-DD"
              required
              value={parseYMD(form.values.valid_from)}
              onChange={(date) =>
                form.setFieldValue(
                  "valid_from",
                  date ? toLocalYMD(date) : "",
                )
              }
              error={form.errors.valid_from}
            />
            <DateInput
              label={t("contracts.form.valid_to")}
              placeholder="2027-01-01"
              valueFormat="YYYY-MM-DD"
              required
              value={parseYMD(form.values.valid_to)}
              onChange={(date) =>
                form.setFieldValue(
                  "valid_to",
                  date ? toLocalYMD(date) : "",
                )
              }
              error={form.errors.valid_to}
            />
          </Group>

          <Select
            label={t("contracts.form.contract_type")}
            data={contractTypeOptions}
            {...form.getInputProps("contract_type")}
            allowDeselect={false}
          />

          <TextInput
            label={t("contracts.form.branch_id")}
            placeholder="UUID (ixtiyoriy)"
            description={t("contracts.form.branch_id_hint")}
            {...form.getInputProps("branch_id")}
          />

          <Group justify="flex-end" mt="md">
            <Button variant="subtle" onClick={handleClose} disabled={isPending}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" loading={isPending}>
              {isEdit ? t("common.save") : t("common.create")}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
