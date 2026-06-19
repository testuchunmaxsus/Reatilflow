/**
 * Tickets feature tiplaari — backend schemas.py ga mos.
 *
 * Backend endpointlari (tickets/router.py):
 *   GET    /tickets               — PaginatedTickets
 *   POST   /tickets               — TicketOut (201)
 *   GET    /tickets/{id}          — TicketOut (messages bilan)
 *   POST   /tickets/{id}/messages — TicketMessageOut (201)
 *   PATCH  /tickets/{id}/status   — TicketOut (holat mashinasi)
 *
 * Holat mashinasi:
 *   new → in_progress → resolved → closed
 *   resolved → in_progress (qayta ochish)
 */

// ─── Xabar ────────────────────────────────────────────────────────────────────

export interface TicketMessageOut {
  id: string;
  ticket_id: string;
  author_id: string | null;
  body: string;
  attachment_url: string | null;
  created_at: string;
}

// ─── Javob ────────────────────────────────────────────────────────────────────

export type TicketStatus = "new" | "in_progress" | "resolved" | "closed";
export type TicketType = "taklif" | "etiroz";

export interface TicketOut {
  id: string;
  store_id: string | null;
  author_id: string | null;
  ticket_type: TicketType;
  subject: string;
  body: string;
  status: TicketStatus;
  assigned_to: string | null;
  branch_id: string | null;
  client_uuid: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  messages: TicketMessageOut[] | null;
}

// ─── Paginated ────────────────────────────────────────────────────────────────

export interface PaginatedTickets {
  items: TicketOut[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Yaratish ─────────────────────────────────────────────────────────────────

export interface TicketCreate {
  ticket_type: TicketType;
  subject: string;
  body: string;
  store_id?: string | null;
  branch_id?: string | null;
  client_uuid?: string | null;
}

// ─── Holat yangilash ──────────────────────────────────────────────────────────

export interface TicketStatusUpdate {
  status: TicketStatus;
  version: number;
}

// ─── Xabar yaratish ───────────────────────────────────────────────────────────

export interface TicketMessageCreate {
  body: string;
  attachment_url?: string | null;
}

// ─── Filtrlar ─────────────────────────────────────────────────────────────────

export interface TicketFilters {
  status?: TicketStatus | "";
  ticket_type?: TicketType | "";
  store_id?: string;
  limit?: number;
  offset?: number;
}
