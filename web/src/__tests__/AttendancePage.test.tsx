/**
 * AttendancePage smoke testi.
 *
 * Tekshiriladi:
 * 1. Sahifa sarlavhasi ko'rsatiladi
 * 2. Davomat yozuvlari jadvalda ko'rsatiladi
 * 3. Bo'sh holat ko'rsatiladi
 * 4. check_out_at null bo'lsa — "—" ko'rsatiladi
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";
import type { AuthUser } from "@/auth/AuthContext";

// ─── Mock ma'lumotlar ─────────────────────────────────────────────────────────

const mockAttendance = {
  items: [
    {
      id: "att-001",
      user_id: "user-aaaabbbbccccdddd",
      work_date: "2026-06-20",
      check_in_at:  "2026-06-20T09:00:00Z",
      check_in_gps_lat:  "41.2995",
      check_in_gps_lng:  "69.2401",
      check_out_at: "2026-06-20T18:00:00Z",
      check_out_gps_lat: "41.2995",
      check_out_gps_lng: "69.2401",
      biometric_verified: true,
      source: "device_fingerprint",
      client_uuid: null,
      version: 1,
      created_at: "2026-06-20T09:00:00Z",
      updated_at: "2026-06-20T18:00:00Z",
      deleted_at: null,
    },
    {
      id: "att-002",
      user_id: "user-eeeeffff00001111",
      work_date: "2026-06-20",
      check_in_at:  "2026-06-20T08:45:00Z",
      check_in_gps_lat:  "41.2990",
      check_in_gps_lng:  "69.2400",
      check_out_at: null,
      check_out_gps_lat: null,
      check_out_gps_lng: null,
      biometric_verified: true,
      source: "device_faceid",
      client_uuid: null,
      version: 1,
      created_at: "2026-06-20T08:45:00Z",
      updated_at: "2026-06-20T08:45:00Z",
      deleted_at: null,
    },
  ],
  total: 2,
  limit: 20,
  offset: 0,
};

const mockEmpty = { items: [], total: 0, limit: 20, offset: 0 };

// ─── API mock ─────────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let attendanceResponse: any = mockAttendance;

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn((path: string) => {
        if (path.startsWith("/attendance"))
          return Promise.resolve(attendanceResponse);
        return Promise.resolve({});
      }),
      post:   vi.fn(() => Promise.resolve({})),
      patch:  vi.fn(() => Promise.resolve({})),
      delete: vi.fn(() => Promise.resolve(undefined)),
    },
  };
});

// ─── Auth mock ────────────────────────────────────────────────────────────────

const adminUser: AuthUser = {
  id: "admin-001",
  phone: "+998901234567",
  full_name: "Admin Test",
  role: "administrator",
  branch_id: null,
  locale: "uz",
  is_active: true,
  biometric_enrolled: false,
  permissions: ["attendance:view"],
};

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({
    user: adminUser,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
  }),
}));

// ─── Render yordamchisi ───────────────────────────────────────────────────────

import { AttendanceListPage } from "@/features/attendance/AttendanceListPage";

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <MemoryRouter>
          <AttendanceListPage />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("AttendanceListPage — smoke", () => {
  beforeEach(() => {
    attendanceResponse = mockAttendance;
    vi.clearAllMocks();
  });

  it("sahifa sarlavhasi ko'rsatiladi", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/davomat/i)).toBeInTheDocument();
    });
  });

  it("davomat yozuvlari jadvalda ko'rsatiladi", async () => {
    renderPage();

    await waitFor(() => {
      // user_id qisqa shakli: birinchi 8 belgi
      expect(screen.getByText(/user-aaa/i)).toBeInTheDocument();
    });
  });

  it("check_out_at null bo'lsa jadvalda — ko'rsatiladi", async () => {
    renderPage();

    await waitFor(() => {
      // att-002 uchun check_out_at null — "—" ko'rsatilishi kerak
      const dashes = screen.getAllByText("—");
      expect(dashes.length).toBeGreaterThan(0);
    });
  });

  it("bo'sh holat xabari ko'rsatiladi", async () => {
    attendanceResponse = mockEmpty;
    renderPage();

    await waitFor(() => {
      expect(
        screen.getByText(/davomat yozuvlari topilmadi/i),
      ).toBeInTheDocument();
    });
  });
});
