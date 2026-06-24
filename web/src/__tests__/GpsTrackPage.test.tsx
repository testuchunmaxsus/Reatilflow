/**
 * GpsTrackPage smoke test
 *
 * Tekshiriladi:
 * 1. Sahifa sarlavhasi ko'rsatiladi
 * 2. Filtr maydonlari ko'rsatiladi
 * 3. GPS nuqtalar kelganda jadval ko'rsatiladi
 * 4. Bo'sh holat ko'rsatiladi
 * 5. Xarita konteyneri yoki fallback render bo'ladi
 *
 * Leaflet window ob'ektlari jsdom da yo'q — react-leaflet mock qilinadi.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MantineProvider } from "@mantine/core";

// ─── Leaflet va react-leaflet mock (jsdom da DOM/Canvas API yo'q) ─────────────

vi.mock("leaflet", () => ({
  default: {
    Icon: {
      Default: {
        prototype: {},
        mergeOptions: vi.fn(),
      },
    },
    divIcon: vi.fn(() => ({ options: {}, _initHooksCalled: true })),
    icon: vi.fn(() => ({ options: {}, _initHooksCalled: true })),
  },
  Icon: {
    Default: {
      prototype: {},
      mergeOptions: vi.fn(),
    },
  },
  divIcon: vi.fn(() => ({ options: {}, _initHooksCalled: true })),
  icon: vi.fn(() => ({ options: {}, _initHooksCalled: true })),
}));

vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="gps-map-container">{children}</div>
  ),
  TileLayer: () => <div data-testid="tile-layer" />,
  Marker: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="map-marker">{children}</div>
  ),
  Polyline: () => <div data-testid="map-polyline" />,
  Popup: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="map-popup">{children}</div>
  ),
}));

// leaflet CSS import ni ham mock qilamiz
vi.mock("leaflet/dist/leaflet.css", () => ({}));

// ─── Mock ma'lumotlar ─────────────────────────────────────────────────────────

const mockTrack = {
  items: [
    {
      id: "gps-001",
      user_id: "user-001",
      delivery_id: null,
      lat: "41.299496",
      lng: "69.240073",
      recorded_at: "2026-06-24T08:00:00Z",
      speed: "1.5",
      ingested_at: "2026-06-24T08:00:01Z",
      created_at: "2026-06-24T08:00:01Z",
    },
    {
      id: "gps-002",
      user_id: "user-001",
      delivery_id: null,
      lat: "41.300000",
      lng: "69.241000",
      recorded_at: "2026-06-24T08:01:00Z",
      speed: "2.0",
      ingested_at: "2026-06-24T08:01:01Z",
      created_at: "2026-06-24T08:01:01Z",
    },
  ],
  total: 2,
  limit: 500,
  offset: 0,
};

const mockTrackEmpty = { items: [], total: 0, limit: 500, offset: 0 };

// ─── API mock ─────────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let trackResponse: any = mockTrack;

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn((path: string) => {
        if (path.startsWith("/gps/track")) return Promise.resolve(trackResponse);
        if (path.startsWith("/users")) return Promise.resolve({ items: [], total: 0, limit: 100, offset: 0 });
        return Promise.resolve({});
      }),
      post: vi.fn(() => Promise.resolve({})),
      patch: vi.fn(() => Promise.resolve({})),
      delete: vi.fn(() => Promise.resolve(undefined)),
    },
  };
});

// ─── Auth mock ────────────────────────────────────────────────────────────────

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({
    user: {
      id: "admin-001",
      phone: "+998901234567",
      full_name: "Admin Test",
      role: "administrator",
      branch_id: null,
      locale: "uz",
      is_active: true,
      biometric_enrolled: false,
      permissions: ["gps:view"],
    },
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
  }),
}));

// ─── Render yordamchisi ───────────────────────────────────────────────────────

import { GpsTrackPage } from "@/features/gps/GpsTrackPage";

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <MemoryRouter>
          <GpsTrackPage />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("GpsTrackPage — smoke test", () => {
  beforeEach(() => {
    trackResponse = mockTrack;
    vi.clearAllMocks();
  });

  it("sahifa sarlavhasi ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/GPS kuzatuv/i)).toBeInTheDocument();
    });
  });

  it("filtr maydonlari ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByPlaceholderText(/UUID/i),
      ).toBeInTheDocument();
    });
  });

  it("GPS nuqtalar kelganda xarita konteyneri ko'rsatiladi", async () => {
    renderPage();
    await waitFor(() => {
      // mock MapContainer data-testid="gps-map-container" render bo'lishi kerak
      const maps = screen.getAllByTestId("gps-map-container");
      expect(maps.length).toBeGreaterThan(0);
    });
  });

  it("fleet mode: faol hodimlar jadvali ko'rsatiladi", async () => {
    // Default (user_id yo'q) — fleet mode. Kenglik jadvali emas,
    // fleet summary jadvali ko'rinadi: "Faol hodimlar" sarlavhasi bilan.
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/Faol hodimlar/i)).toBeInTheDocument();
    });
    // Foydalanuvchi IDsi bir nechta joyda (popup + jadval) ko'rsatilishi mumkin
    await waitFor(() => {
      const items = screen.getAllByText(/user-001/i);
      expect(items.length).toBeGreaterThan(0);
    });
  });

  it("bo'sh holat ko'rsatiladi", async () => {
    trackResponse = mockTrackEmpty;
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByTestId("gps-no-data"),
      ).toBeInTheDocument();
    });
  });

  it("filtr qo'llash tugmasi bosilganda API chaqiriladi", async () => {
    const { apiClient } = await import("@/api/client");
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/GPS kuzatuv/i)).toBeInTheDocument();
    });

    // Saqlash button (common.save key — uz.json da "Saqlash")
    const applyBtn = screen.getByRole("button", { name: /saqlash/i });
    fireEvent.click(applyBtn);

    await waitFor(() => {
      expect(apiClient.get).toHaveBeenCalledWith(
        expect.stringContaining("/gps/track"),
      );
    });
  });
});
