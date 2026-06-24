/**
 * Davomat tiplaari — T16.
 *
 * Backend endpoint: GET /attendance (PaginatedAttendance)
 * Backend sxema:    AttendanceOut, PaginatedAttendance
 */

// ─── Biometriya manbai ────────────────────────────────────────────────────────

export type AttendanceSource = "device_faceid" | "device_fingerprint";

// ─── Davomat yozuvi ───────────────────────────────────────────────────────────

export interface AttendanceOut {
  id: string;
  user_id: string;
  work_date: string;           // "YYYY-MM-DD"
  check_in_at: string;         // ISO 8601 datetime
  check_in_gps_lat: string;    // Decimal → string JSON da
  check_in_gps_lng: string;
  check_out_at: string | null;
  check_out_gps_lat: string | null;
  check_out_gps_lng: string | null;
  biometric_verified: boolean;
  source: AttendanceSource | string;
  client_uuid: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

// ─── Paginated javob ──────────────────────────────────────────────────────────

export interface PaginatedAttendance {
  items: AttendanceOut[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Filtr parametrlari ───────────────────────────────────────────────────────

export interface AttendanceFilters {
  user_id?: string;
  date?: string;       // "YYYY-MM-DD"
  limit?: number;
  offset?: number;
}
