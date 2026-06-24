/**
 * GPS feature tiplaari — backend schemas.py ga mos.
 *
 * Endpointlar:
 *   GET  /gps/track              — foydalanuvchi+sana bo'yicha marshrut
 *   GET  /gps/track/{delivery_id} — yetkazish marshrutini ko'rish
 *
 * RBAC:
 *   gps:view — agent, courier (faqat o'ziniki), administrator (barchasi)
 */

// ─── GPS nuqta ────────────────────────────────────────────────────────────────

/** GET /gps/track javobidagi bitta nuqta (GpsTrackOut → frontend mos) */
export interface GpsPoint {
  id: string;
  user_id: string;
  delivery_id: string | null;
  /** Kenglik — backend Decimal, frontend string yoki number */
  lat: number | string;
  /** Uzunlik */
  lng: number | string;
  recorded_at: string;
  speed: number | string | null;
  ingested_at: string;
  created_at: string;
}

// ─── Paginated javob ──────────────────────────────────────────────────────────

export interface PaginatedTrack {
  items: GpsPoint[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Filtrlar ─────────────────────────────────────────────────────────────────

export interface GpsTrackFilters {
  user_id?: string;
  date?: string;     // YYYY-MM-DD
  limit?: number;
  offset?: number;
}
