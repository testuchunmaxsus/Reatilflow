/**
 * GpsTrackPage — GPS trek xarita sahifasi.
 *
 * Xususiyatlar:
 *   - Leaflet + OpenStreetMap (API key kerak emas)
 *   - Marker va Polyline — GPS nuqtalarini ko'rsatadi
 *   - Filtrlar: user_id, sana
 *   - RBAC: admin barchani, agent/courier faqat o'zini ko'radi
 *   - Leaflet CSS import qilinadi
 *   - react-leaflet render xatosi bo'lsa — jadval + OSM havola fallback
 *
 * i18n: gps.* kalitlari + defaultValue fallback.
 */

import "leaflet/dist/leaflet.css";

import {
  Box,
  Button,
  Group,
  Loader,
  Paper,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import L from "leaflet";
import { Component } from "react";
import type { ReactNode } from "react";
import { MapContainer, TileLayer, Marker, Polyline, Popup } from "react-leaflet";
import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useGpsTrack } from "./api/gpsApi";
import type { GpsPoint } from "./types";

// ─── Leaflet default icon tuzatish (Vite PNG yo'llari muammosi) ──────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: new URL(
    "leaflet/dist/images/marker-icon-2x.png",
    import.meta.url,
  ).href,
  iconUrl: new URL(
    "leaflet/dist/images/marker-icon.png",
    import.meta.url,
  ).href,
  shadowUrl: new URL(
    "leaflet/dist/images/marker-shadow.png",
    import.meta.url,
  ).href,
});

// ─── Koordinata float'ga aylantirish yordamchisi ──────────────────────────────

function toFloat(v: number | string | null | undefined): number {
  if (v === null || v === undefined) return 0;
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n) ? 0 : n;
}

// FIX #8: koordinatasi yaroqsiz (NaN yoki 0,0 "null island") nuqtalarni
// marker/polyline dan tashlab yuborish uchun — Number.isFinite tekshiruvi.
function isValidCoord(lat: number | string | null | undefined, lng: number | string | null | undefined): boolean {
  const la = toFloat(lat);
  const ln = toFloat(lng);
  return Number.isFinite(la) && Number.isFinite(ln) && (la !== 0 || ln !== 0);
}

// ─── Vaqt formatlash ─────────────────────────────────────────────────────────

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

// ─── Fallback: oddiy jadval + OSM havola ─────────────────────────────────────

interface FallbackProps {
  points: GpsPoint[];
}

function GpsMapFallback({ points }: FallbackProps) {
  const { t } = useTranslation();
  const last = points[points.length - 1];
  const osmUrl = last
    ? `https://www.openstreetmap.org/?mlat=${toFloat(last.lat)}&mlon=${toFloat(last.lng)}#map=15/${toFloat(last.lat)}/${toFloat(last.lng)}`
    : null;

  return (
    <Stack gap="sm" data-testid="gps-map-fallback">
      {osmUrl && (
        <Group p="xs">
          <Button
            component="a"
            href={osmUrl}
            target="_blank"
            rel="noopener noreferrer"
            variant="light"
            size="sm"
          >
            {t("gps.map.title", { defaultValue: "Xarita" })} (OpenStreetMap)
          </Button>
        </Group>
      )}
      <Table.ScrollContainer minWidth={600}>
        <Table striped withTableBorder>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>#</Table.Th>
              <Table.Th>
                {t("gps.table.lat", { defaultValue: "Kenglik" })}
              </Table.Th>
              <Table.Th>
                {t("gps.table.lng", { defaultValue: "Uzunlik" })}
              </Table.Th>
              <Table.Th>
                {t("gps.table.last_seen", { defaultValue: "Vaqt" })}
              </Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {points.slice(0, 50).map((p, i) => (
              <Table.Tr key={p.id}>
                <Table.Td>
                  <Text size="sm" c="dimmed">
                    {i + 1}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" ff="monospace">
                    {toFloat(p.lat).toFixed(6)}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" ff="monospace">
                    {toFloat(p.lng).toFixed(6)}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" c="dimmed">
                    {fmtTime(p.recorded_at)}
                  </Text>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Stack>
  );
}

// ─── Error boundary — react-leaflet render xatosini ushlab qolish ─────────────

interface EBState {
  hasError: boolean;
}

class MapErrorBoundary extends Component<
  { children: ReactNode; fallback: ReactNode },
  EBState
> {
  constructor(props: { children: ReactNode; fallback: ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): EBState {
    return { hasError: true };
  }

  override render() {
    if (this.state.hasError) {
      return this.props.fallback;
    }
    return this.props.children;
  }
}

// ─── Leaflet xarita komponenti ────────────────────────────────────────────────

interface MapViewProps {
  points: GpsPoint[];
}

function GpsLeafletMap({ points }: MapViewProps) {
  const { t } = useTranslation();

  // FIX #8: yaroqsiz koordinatali nuqtalarni tashlab yuborish (0,0 null island, NaN)
  const validPoints = points.filter((p) => isValidCoord(p.lat, p.lng));

  if (validPoints.length === 0) {
    return (
      <Box py="xl" ta="center" data-testid="gps-no-valid-coords">
        <Text c="dimmed">
          {t("gps.map.no_valid_coords", { defaultValue: "Yaroqli koordinatalar topilmadi" })}
        </Text>
      </Box>
    );
  }

  const center: [number, number] = [
    toFloat(validPoints[0].lat),
    toFloat(validPoints[0].lng),
  ];

  const polylinePositions: [number, number][] = validPoints.map((p) => [
    toFloat(p.lat),
    toFloat(p.lng),
  ]);

  // FIX #8: lastPoint ham validPoints ichidan (yaroqli koordinata bilan)
  const lastPoint = validPoints[validPoints.length - 1];

  return (
    <Box
      style={{ height: 480, borderRadius: 8, overflow: "hidden" }}
      data-testid="gps-map-wrapper"
    >
      <MapContainer
        data-testid="gps-map-container"
        center={center}
        zoom={13}
        style={{ height: "100%", width: "100%" }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {/* Marshrut chizig'i — faqat yaroqli nuqtalar */}
        <Polyline positions={polylinePositions} color="#228be6" weight={3} />
        {/* Boshlang'ich nuqta — validPoints[0] */}
        <Marker position={[toFloat(validPoints[0].lat), toFloat(validPoints[0].lng)]}>
          <Popup>
            {t("gps.map.track_history", { defaultValue: "Harakat tarixi" })}{" "}
            — {fmtTime(validPoints[0].recorded_at)}
          </Popup>
        </Marker>
        {/* Oxirgi nuqta (joriy joylashuv) — faqat validPoints.length > 1 */}
        {validPoints.length > 1 && (
          <Marker
            position={[toFloat(lastPoint.lat), toFloat(lastPoint.lng)]}
          >
            <Popup>
              {t("gps.map.current_location", {
                defaultValue: "Joriy joylashuv",
              })}{" "}
              — {fmtTime(lastPoint.recorded_at)}
            </Popup>
          </Marker>
        )}
      </MapContainer>
    </Box>
  );
}

function GpsMapView({ points }: MapViewProps) {
  const { t } = useTranslation();

  if (points.length === 0) {
    return (
      <Box py="xl" ta="center" data-testid="gps-no-data">
        <Text c="dimmed">
          {t("gps.map.no_data", { defaultValue: "Xarita uchun ma'lumot yo'q" })}
        </Text>
      </Box>
    );
  }

  return (
    <MapErrorBoundary fallback={<GpsMapFallback points={points} />}>
      <GpsLeafletMap points={points} />
    </MapErrorBoundary>
  );
}

// ─── Asosiy sahifa ────────────────────────────────────────────────────────────

export function GpsTrackPage() {
  const { t } = useTranslation();

  const today = new Date().toISOString().split("T")[0];
  const [userId, setUserId] = useState("");
  const [date, setDate] = useState(today);
  const [appliedFilters, setAppliedFilters] = useState<{
    user_id?: string;
    date?: string;
  }>({ date: today });

  // Sahifa yuklanganda joriy sana bilan qidirish
  useEffect(() => {
    setAppliedFilters({ date: today });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const { data, isLoading, isError, error } = useGpsTrack({
    user_id: appliedFilters.user_id,
    date: appliedFilters.date,
    limit: 500,
    offset: 0,
  });

  const points = data?.items ?? [];

  function handleApply() {
    setAppliedFilters({
      user_id: userId.trim() || undefined,
      date: date || undefined,
    });
  }

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Title order={3}>
          {t("gps.title", { defaultValue: "GPS kuzatuv" })}
        </Title>
        <Text size="sm" c="dimmed">
          {t("gps.map.track_history", { defaultValue: "Harakat tarixi" })}
        </Text>
      </Group>

      {/* Filtrlar */}
      <Paper withBorder p="sm" radius="md">
        <Group gap="sm" wrap="wrap">
          <TextInput
            label={t("gps.filter.user", { defaultValue: "Foydalanuvchi bo'yicha" })}
            placeholder="UUID"
            value={userId}
            onChange={(e) => setUserId(e.currentTarget.value)}
            w={260}
          />
          <TextInput
            label={t("gps.filter.from", { defaultValue: "Sana" })}
            type="date"
            value={date}
            onChange={(e) => setDate(e.currentTarget.value)}
            w={180}
          />
          <Box style={{ alignSelf: "flex-end" }}>
            <Button onClick={handleApply} size="sm">
              {t("common.save", { defaultValue: "Qo'llash" })}
            </Button>
          </Box>
        </Group>
      </Paper>

      {/* Yuklanish / xato */}
      {isLoading ? (
        <Group justify="center" py="xl">
          <Loader />
          <Text c="dimmed">{t("common.loading", { defaultValue: "Yuklanmoqda..." })}</Text>
        </Group>
      ) : isError ? (
        <Box py="xl" ta="center">
          <Text c="red">
            {error instanceof Error
              ? error.message
              : t("errors.unknown", { defaultValue: "Noma'lum xato" })}
          </Text>
        </Box>
      ) : (
        <>
          {/* Xarita */}
          <Paper withBorder radius="md" style={{ overflow: "hidden" }}>
            <Box p="xs">
              <Text fw={600} size="sm" mb="xs">
                {t("gps.map.title", { defaultValue: "Xarita" })}
                {points.length > 0 && (
                  <Text component="span" c="dimmed" size="xs" ml="xs">
                    ({points.length} ta nuqta)
                  </Text>
                )}
              </Text>
            </Box>
            <GpsMapView points={points} />
          </Paper>

          {/* Nuqtalar jadvali */}
          {points.length > 0 && (
            <Paper withBorder p="sm" radius="md">
              <Text fw={600} size="sm" mb="xs">
                {t("gps.history.title", { defaultValue: "Harakat tarixi" })}
              </Text>
              <Table.ScrollContainer minWidth={700}>
                <Table striped highlightOnHover withTableBorder>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>#</Table.Th>
                      <Table.Th>
                        {t("gps.table.lat", { defaultValue: "Kenglik" })}
                      </Table.Th>
                      <Table.Th>
                        {t("gps.table.lng", { defaultValue: "Uzunlik" })}
                      </Table.Th>
                      <Table.Th>
                        {t("gps.table.last_seen", { defaultValue: "Vaqt" })}
                      </Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {points.slice(0, 100).map((p, i) => (
                      <Table.Tr key={p.id}>
                        <Table.Td>
                          <Text size="xs" c="dimmed">
                            {i + 1}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          <Text size="xs" ff="monospace">
                            {toFloat(p.lat).toFixed(6)}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          <Text size="xs" ff="monospace">
                            {toFloat(p.lng).toFixed(6)}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          <Text size="xs" c="dimmed">
                            {fmtTime(p.recorded_at)}
                          </Text>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
              {points.length > 100 && (
                <Text size="xs" c="dimmed" mt="xs" ta="center">
                  {points.length - 100}{" "}
                  {t("gps.history.empty", {
                    defaultValue: "ta qo'shimcha nuqta...",
                  })}
                </Text>
              )}
            </Paper>
          )}

          {points.length === 0 && !isLoading && (
            <Box py="xl" ta="center">
              <Text c="dimmed">
                {t("gps.table.empty", {
                  defaultValue: "GPS ma'lumotlari topilmadi",
                })}
              </Text>
            </Box>
          )}
        </>
      )}
    </Stack>
  );
}
