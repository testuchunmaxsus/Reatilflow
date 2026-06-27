/**
 * Import API — Excel va Nakladnoy rasm import endpointlari.
 *
 * ADR-010 Variant C: stateless parse + client-held preview.
 * - POST /import/excel/parse    → ExcelParseOut (DBga yozilmaydi)
 * - POST /import/nakladnoy/parse → NakladnoyParseOut
 * - POST /import/confirm        → ImportConfirmOut (create)
 *
 * apiClient.upload (FormData) va apiClient.post (JSON) naqshlari.
 */

import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/api/client";

// ─── Tiplar ──────────────────────────────────────────────────────────────────

export interface ColumnMapping {
  source_header: string;
  mapped_to: string;
  confidence: number;
}

export interface ParsedRow {
  name: string;
  sku: string | null;
  barcode: string | null;
  qty: number;
  price: number;
  currency: string;
  expiry_date: string | null;
  row_index: number;
  confidence?: number;
  /** client tomonidan qo'shiladi — preview da tahrir uchun */
  client_uuid?: string;
}

export interface ExcelParseOut {
  columns_detected: ColumnMapping[];
  rows: ParsedRow[];
  warnings: string[];
  parse_id: string;
}

export interface NakladnoyParseOut {
  rows: ParsedRow[];
  raw_text: string | null;
  warnings: string[];
  vision_enabled: boolean;
}

export type ImportSource = "excel" | "nakladnoy";

export interface ConfirmRow {
  name: string;
  sku?: string | null;
  barcode?: string | null;
  qty: number;
  price: number;
  currency: string;
  expiry_date?: string | null;
  client_uuid: string;
}

export interface ImportConfirmIn {
  source: ImportSource;
  rows: ConfirmRow[];
}

export interface RowError {
  row_index: number;
  code: string;
  message: string;
}

export interface ImportConfirmOut {
  created: number;
  skipped: number;
  errors: RowError[];
  target: "catalog" | "store_inventory";
}

// ─── Excel parse mutation ────────────────────────────────────────────────────

export function useParseExcel() {
  return useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      return apiClient.upload<ExcelParseOut>("/import/excel/parse", formData);
    },
  });
}

// ─── Nakladnoy rasm parse mutation ──────────────────────────────────────────

export function useParseNakladnoy() {
  return useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      return apiClient.upload<NakladnoyParseOut>(
        "/import/nakladnoy/parse",
        formData,
      );
    },
  });
}

// ─── Confirm (create) mutation ───────────────────────────────────────────────

export function useImportConfirm() {
  return useMutation({
    mutationFn: (data: ImportConfirmIn) =>
      apiClient.post<ImportConfirmOut>("/import/confirm", data),
  });
}
