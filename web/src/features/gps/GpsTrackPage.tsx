/**
 * GpsTrackPage — GPS fleet monitoring xarita sahifasi.
 *
 * Fleet view (default, user_id filtr bo'sh):
 *   - Har bir foydalanuvchi uchun ALOHIDA marker — eng oxirgi nuqtada.
 *   - Agentlar ko'k, kuryerlar yashil rangli divIcon.
 *   - Har foydalanuvchining to'liq treki — alohida rangli polyline.
 *   - Marker popup: ism, rol, oxirgi ko'ringan vaqt.
 *
 * Single-user view (user_id berilgan):
 *   - O'sha foydalanuvchining to'liq treki + boshlang'ich/oxirgi marker.
 *
 * Foydalanuvchi filtri:
 *   - TextInput (UUID) — test compatibility saqlanadi.
 *   - Qo'shimcha Select (foydalanuvchilar ro'yxatidan, agent+courier).
 *
 * i18n: gps.* kalitlari + defaultValue fallback.
 * RBAC: admin barchani, agent/courier faqat o'zini ko'radi.
 * react-leaflet: MapErrorBoundary + GpsMapFallback saqlanadi.
 */

import "leaflet/dist/leaflet.css";

import {
  Box,
  Button,
  Group,
  Loader,
  Paper,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { UuidHelp } from "@/components/UuidHelp";
import L from "leaflet";
import { Component } from "react";
import type { ReactNode } from "react";
import { MapContainer, TileLayer, Marker, Polyline, Popup } from "react-leaflet";
import { useState, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useGpsTrack } from "./api/gpsApi";
import { useUsers } from "@/features/users/api/usersApi";
import { formatDateTime } from "@/utils/date";
import type { GpsPoint } from "./types";
import type { UserOut } from "@/features/users/types";

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

// ─── Rang konstantalari (agent = ko'k, courier = yashil, boshqa = to'q sariq) ─

const ROLE_COLORS: Record<string, string> = {
  agent: "#228be6",
  courier: "#40c057",
};

const POLYLINE_COLORS = [
  "#228be6", "#40c057", "#fa5252", "#fd7e14", "#7950f2",
  "#15aabf", "#e64980", "#82c91e", "#fab005", "#339af0",
];

// ─── Rangli divIcon yaratish ──────────────────────────────────────────────────

function createColoredIcon(color: string): L.DivIcon {
  return L.divIcon({
    className: "",
    html: `<div style="
      width: 22px;
      height: 22px;
      border-radius: 50%;
      background: ${color};
      border: 3px solid #fff;
      box-shadow: 0 1px 4px rgba(0,0,0,0.4);
    "></div>`,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
    popupAnchor: [0, -14],
  });
}

function getRoleColor(role: string | undefined): string {
  return ROLE_COLORS[role ?? ""] ?? "#868e96";
}

// ─── Koordinata yordamchilari ─────────────────────────────────────────────────

function toFloat(v: number | string | null | undefined): number {
  if (v === null || v === undefined) return 0;
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n) ? 0 : n;
}

function isValidCoord(
  lat: number | string | null | undefined,
  lng: number | string | null | undefined,
): boolean {
  const la = toFloat(lat);
  const ln = toFloat(lng);
  return Number.isFinite(la) && Number.isFinite(ln) && (la !== 0 || ln !== 0);
}

// ─── UUID qisqartirish ────────────────────────────────────────────────────────

function shortId(id: string): string {
  return id.length > 8 ? `${id.slice(0, 8)}…` : id;
}

// ─── Foydalanuvchi nomi yordamchisi ──────────────────────────────────────────

function userLabel(userId: string, userMap: Map<string, UserOut>): string {
  const u = userMap.get(userId);
  return u ? u.full_name : shortId(userId);
}

function userRole(userId: string, userMap: Map<string, UserOut>): string | undefined {
  return userMap.get(userId)?.role;
}

// ─── GPS nuqtalarini user_id bo'yicha guruhlash ───────────────────────────────

function groupByUser(points: GpsPoint[]): Map<string, GpsPoint[]> {
  const map = new Map<string, GpsPoint[]>();
  for (const p of points) {
    if (!isValidCoord(p.lat, p.lng)) continue;
    const arr = map.get(p.user_id) ?? [];
    arr.push(p);
    map.set(p.user_id, arr);
  }
  // Har guruh ichida vaqt bo'yicha saralash (eng eski → eng yangi)
  for (const [, arr] of map) {
    arr.sort((a, b) => a.recorded_at.localeCompare(b.recorded_at));
  }
  return map;
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
              <Table.Th>{t("gps.table.lat", { defaultValue: "Kenglik" })}</Table.Th>
              <Table.Th>{t("gps.table.lng", { defaultValue: "Uzunlik" })}</Table.Th>
              <Table.Th>{t("gps.table.last_seen", { defaultValue: "Vaqt" })}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {points.slice(0, 50).map((p, i) => (
              <Table.Tr key={p.id}>
                <Table.Td>
                  <Text size="sm" c="dimmed">{i + 1}</Text>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" ff="monospace">{toFloat(p.lat).toFixed(6)}</Text>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" ff="monospace">{toFloat(p.lng).toFixed(6)}</Text>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" c="dimmed">{formatDateTime(p.recorded_at)}</Text>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Stack>
  );
}

// ─── Error boundary — react-leaflet render xatosini ushlab qolish ────────────

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

// ─── Fleet Leaflet xaritasi (user_id bo'sh — barcha agentlar/kuryerlar) ──────

interface FleetMapProps {
  grouped: Map<string, GpsPoint[]>;
  userMap: Map<string, UserOut>;
}

function FleetLeafletMap({ grouped, userMap }: FleetMapProps) {
  const { t } = useTranslation();

  // Xarita markazi: barcha oxirgi nuqtalar o'rtasi
  const lastPoints = useMemo(() => {
    const pts: Array<{ userId: string; point: GpsPoint }> = [];
    for (const [userId, arr] of grouped) {
      const last = arr[arr.length - 1];
      if (last) pts.push({ userId, point: last });
    }
    return pts;
  }, [grouped]);

  if (lastPoints.length === 0) {
    return null; // GpsFleetMapView da bo'sh holat ko'rsatiladi
  }

  // Markazni hisoblash — o'rta nuqta
  const avgLat =
    lastPoints.reduce((s, { point: p }) => s + toFloat(p.lat), 0) /
    lastPoints.length;
  const avgLng =
    lastPoints.reduce((s, { point: p }) => s + toFloat(p.lng), 0) /
    lastPoints.length;
  const center: [number, number] = [avgLat, avgLng];

  // Zoom: bir nechta marker bo'lsa 12, bitta bo'lsa 14
  const zoom = lastPoints.length === 1 ? 14 : 12;

  const userIds = Array.from(grouped.keys());

  return (
    <Box
      style={{ height: 480, borderRadius: 8, overflow: "hidden" }}
      data-testid="gps-map-wrapper"
    >
      <MapContainer
        data-testid="gps-map-container"
        center={center}
        zoom={zoom}
        style={{ height: "100%", width: "100%" }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {/* Har foydalanuvchi uchun polyline + oxirgi marker */}
        {userIds.map((userId, idx) => {
          const arr = grouped.get(userId) ?? [];
          const role = userRole(userId, userMap);
          const color = POLYLINE_COLORS[idx % POLYLINE_COLORS.length];
          const markerColor = getRoleColor(role);
          const icon = createColoredIcon(markerColor);
          const lastPt = arr[arr.length - 1];
          const name = userLabel(userId, userMap);
          const roleLabel =
            role === "agent"
              ? t("roles.agent", { defaultValue: "Agent" })
              : role === "courier"
                ? t("roles.courier", { defaultValue: "Kuryer" })
                : role ?? shortId(userId);

          const polyPositions: [number, number][] = arr.map((p) => [
            toFloat(p.lat),
            toFloat(p.lng),
          ]);

          return (
            <span key={userId}>
              {/* Trek chizig'i */}
              {polyPositions.length > 1 && (
                <Polyline
                  positions={polyPositions}
                  color={color}
                  weight={2}
                  opacity={0.6}
                />
              )}
              {/* Oxirgi joylashuv markeri */}
              {lastPt && (
                <Marker
                  position={[toFloat(lastPt.lat), toFloat(lastPt.lng)]}
                  icon={icon}
                >
                  <Popup>
                    <strong>{name}</strong>
                    <br />
                    {roleLabel}
                    <br />
                    <span style={{ fontSize: "0.85em", color: "#666" }}>
                      {t("gps.map.last_seen", { defaultValue: "Oxirgi ko'ringan" })}
                      {": "}
                      {formatDateTime(lastPt.recorded_at)}
                    </span>
                  </Popup>
                </Marker>
              )}
            </span>
          );
        })}
      </MapContainer>
    </Box>
  );
}

// ─── Single-user Leaflet xaritasi (user_id berilgan) ─────────────────────────

interface SingleUserMapProps {
  points: GpsPoint[];
  userMap: Map<string, UserOut>;
}

function SingleUserLeafletMap({ points, userMap }: SingleUserMapProps) {
  const { t } = useTranslation();

  const validPoints = points.filter((p) => isValidCoord(p.lat, p.lng));

  if (validPoints.length === 0) {
    return (
      <Box py="xl" ta="center" data-testid="gps-no-valid-coords">
        <Text c="dimmed">
          {t("gps.map.no_valid_coords", {
            defaultValue: "Yaroqli koordinatalar topilmadi",
          })}
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

  const lastPoint = validPoints[validPoints.length - 1];
  const userId = validPoints[0].user_id;
  const role = userRole(userId, userMap);
  const name = userLabel(userId, userMap);
  const markerColor = getRoleColor(role);
  const icon = createColoredIcon(markerColor);

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
        {/* Trek chizig'i */}
        <Polyline positions={polylinePositions} color={markerColor} weight={3} />
        {/* Boshlang'ich marker */}
        <Marker
          position={[toFloat(validPoints[0].lat), toFloat(validPoints[0].lng)]}
          icon={createColoredIcon("#adb5bd")}
        >
          <Popup>
            <strong>{name}</strong>
            <br />
            {t("gps.map.track_history", { defaultValue: "Harakat tarixi" })}
            {" — "}
            {formatDateTime(validPoints[0].recorded_at)}
          </Popup>
        </Marker>
        {/* Oxirgi marker */}
        {validPoints.length > 1 && (
          <Marker
            position={[toFloat(lastPoint.lat), toFloat(lastPoint.lng)]}
            icon={icon}
          >
            <Popup>
              <strong>{name}</strong>
              <br />
              {t("gps.map.current_location", {
                defaultValue: "Joriy joylashuv",
              })}
              {" — "}
              {formatDateTime(lastPoint.recorded_at)}
            </Popup>
          </Marker>
        )}
      </MapContainer>
    </Box>
  );
}

// ─── GpsMapView — fleet yoki single-user rejimini tanlaydi ───────────────────

interface MapViewProps {
  points: GpsPoint[];
  userMap: Map<string, UserOut>;
  isFleetMode: boolean;
}

function GpsMapView({ points, userMap, isFleetMode }: MapViewProps) {
  const { t } = useTranslation();

  if (points.length === 0) {
    return (
      <Box py="xl" ta="center" data-testid="gps-no-data">
        <Text c="dimmed" maw={480} mx="auto">
          {t("gps.map.fleet_empty", {
            defaultValue:
              "Hozircha hech bir agent/kuryer GPS yubormayapti. Ular faqat ish vaqtida (davomat check-in + mobil ilova ochiq) xaritada ko'rinadi.",
          })}
        </Text>
      </Box>
    );
  }

  if (isFleetMode) {
    const grouped = groupByUser(points);

    if (grouped.size === 0) {
      return (
        <Box py="xl" ta="center" data-testid="gps-no-data">
          <Text c="dimmed">
            {t("gps.map.no_valid_coords", {
              defaultValue: "Yaroqli koordinatalar topilmadi",
            })}
          </Text>
        </Box>
      );
    }

    return (
      <MapErrorBoundary fallback={<GpsMapFallback points={points} />}>
        <FleetLeafletMap grouped={grouped} userMap={userMap} />
      </MapErrorBoundary>
    );
  }

  return (
    <MapErrorBoundary fallback={<GpsMapFallback points={points} />}>
      <SingleUserLeafletMap points={points} userMap={userMap} />
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

  const isFleetMode = !appliedFilters.user_id;

  // GPS nuqtalar
  const { data, isLoading, isError, error } = useGpsTrack({
    user_id: appliedFilters.user_id,
    date: appliedFilters.date,
    limit: 500,
    offset: 0,
  });

  // Foydalanuvchilar ro'yxati (agent + courier) — filtr Select va ism ko'rsatish uchun
  const { data: usersData } = useUsers({
    limit: 100,
    offset: 0,
  });

  const points = data?.items ?? [];

  // user_id -> UserOut map (ism/rol tezkor qidirish)
  const userMap = useMemo<Map<string, UserOut>>(() => {
    const m = new Map<string, UserOut>();
    for (const u of usersData?.items ?? []) {
      m.set(u.id, u);
    }
    return m;
  }, [usersData]);

  // Select options — faqat agent va kuryerlar
  const userSelectOptions = useMemo(() => {
    return (usersData?.items ?? [])
      .filter((u) => u.role === "agent" || u.role === "courier")
      .map((u) => ({
        value: u.id,
        label: `${u.full_name} (${u.role === "agent" ? t("roles.agent", { defaultValue: "Agent" }) : t("roles.courier", { defaultValue: "Kuryer" })})`,
      }));
  }, [usersData, t]);

  function handleApply() {
    setAppliedFilters({
      user_id: userId.trim() || undefined,
      date: date || undefined,
    });
  }

  // Select tanlanganda TextInput ham yangilansin
  function handleSelectUser(value: string | null) {
    setUserId(value ?? "");
  }

  // Fleet view: fleet markers soni
  const fleetCount = useMemo(() => {
    if (!isFleetMode) return 0;
    return groupByUser(points).size;
  }, [isFleetMode, points]);

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Title order={3}>
          {t("gps.title", { defaultValue: "GPS kuzatuv" })}
        </Title>
        <Text size="sm" c="dimmed">
          {isFleetMode
            ? t("gps.map.fleet_view", { defaultValue: "Fleet monitoring" })
            : t("gps.map.track_history", { defaultValue: "Harakat tarixi" })}
        </Text>
      </Group>

      {/* Filtrlar */}
      <Paper withBorder p="sm" radius="md">
        <Group gap="sm" wrap="wrap">
          {/* TextInput — UUID qo'lda kiritish (test compatibility) */}
          <TextInput
            label={
              <Group gap={4} component="span">
                {t("gps.filter.user", { defaultValue: "Foydalanuvchi bo'yicha" })}
                <UuidHelp optional />
              </Group>
            }
            placeholder="UUID"
            value={userId}
            onChange={(e) => setUserId(e.currentTarget.value)}
            w={200}
          />
          {/* Select — agent/kuryerlar ro'yxatidan tanlash (optional, agar yuklangan bo'lsa) */}
          {userSelectOptions.length > 0 && (
            <Select
              label={t("gps.filter.select_user", { defaultValue: "Yoki tanlang" })}
              placeholder={t("gps.filter.all_users", { defaultValue: "Barcha" })}
              data={userSelectOptions}
              value={userId || null}
              onChange={handleSelectUser}
              clearable
              searchable
              w={260}
            />
          )}
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
          <Text c="dimmed">
            {t("common.loading", { defaultValue: "Yuklanmoqda..." })}
          </Text>
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
                {isFleetMode && fleetCount > 0 && (
                  <Text component="span" c="dimmed" size="xs" ml="xs">
                    ({fleetCount}{" "}
                    {t("gps.map.fleet_agents", {
                      defaultValue: "ta agent/kuryer",
                    })}
                    )
                  </Text>
                )}
                {!isFleetMode && points.length > 0 && (
                  <Text component="span" c="dimmed" size="xs" ml="xs">
                    ({points.length}{" "}
                    {t("gps.map.points_count", { defaultValue: "ta nuqta" })})
                  </Text>
                )}
              </Text>
              {/* Rang izoh (fleet rejimida) */}
              {isFleetMode && points.length > 0 && (
                <Group gap="md" mb="xs">
                  <Group gap={4}>
                    <Box
                      style={{
                        width: 12,
                        height: 12,
                        borderRadius: "50%",
                        background: ROLE_COLORS.agent,
                        border: "2px solid #fff",
                        boxShadow: "0 0 0 1px #228be6",
                      }}
                    />
                    <Text size="xs" c="dimmed">
                      {t("roles.agent", { defaultValue: "Agent" })}
                    </Text>
                  </Group>
                  <Group gap={4}>
                    <Box
                      style={{
                        width: 12,
                        height: 12,
                        borderRadius: "50%",
                        background: ROLE_COLORS.courier,
                        border: "2px solid #fff",
                        boxShadow: "0 0 0 1px #40c057",
                      }}
                    />
                    <Text size="xs" c="dimmed">
                      {t("roles.courier", { defaultValue: "Kuryer" })}
                    </Text>
                  </Group>
                </Group>
              )}
            </Box>
            <GpsMapView
              points={points}
              userMap={userMap}
              isFleetMode={isFleetMode}
            />
          </Paper>

          {/* Nuqtalar jadvali (faqat single-user rejimida) */}
          {!isFleetMode && points.length > 0 && (
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
                          <Text size="xs" c="dimmed">{i + 1}</Text>
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
                            {formatDateTime(p.recorded_at)}
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

          {/* Fleet rejimida jadval o'rniga qisqacha ro'yxat */}
          {isFleetMode && points.length > 0 && (
            <Paper withBorder p="sm" radius="md">
              <Text fw={600} size="sm" mb="xs">
                {t("gps.fleet.summary", { defaultValue: "Faol hodimlar" })}
              </Text>
              <Table striped withTableBorder>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>#</Table.Th>
                    <Table.Th>
                      {t("gps.fleet.name", { defaultValue: "Ism" })}
                    </Table.Th>
                    <Table.Th>
                      {t("gps.fleet.role", { defaultValue: "Rol" })}
                    </Table.Th>
                    <Table.Th>
                      {t("gps.table.last_seen", {
                        defaultValue: "Oxirgi ko'ringan",
                      })}
                    </Table.Th>
                    <Table.Th>
                      {t("gps.fleet.points", { defaultValue: "Nuqtalar" })}
                    </Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {Array.from(groupByUser(points).entries()).map(
                    ([uid, arr], i) => {
                      const lastPt = arr[arr.length - 1];
                      const role = userRole(uid, userMap);
                      return (
                        <Table.Tr key={uid}>
                          <Table.Td>
                            <Text size="xs" c="dimmed">{i + 1}</Text>
                          </Table.Td>
                          <Table.Td>
                            <Text size="xs">{userLabel(uid, userMap)}</Text>
                          </Table.Td>
                          <Table.Td>
                            <Text
                              size="xs"
                              c={
                                role === "agent"
                                  ? "blue"
                                  : role === "courier"
                                    ? "green"
                                    : "dimmed"
                              }
                            >
                              {role === "agent"
                                ? t("roles.agent", { defaultValue: "Agent" })
                                : role === "courier"
                                  ? t("roles.courier", {
                                      defaultValue: "Kuryer",
                                    })
                                  : role ?? "—"}
                            </Text>
                          </Table.Td>
                          <Table.Td>
                            <Text size="xs" c="dimmed">
                              {lastPt
                                ? formatDateTime(lastPt.recorded_at)
                                : "—"}
                            </Text>
                          </Table.Td>
                          <Table.Td>
                            <Text size="xs" c="dimmed">{arr.length}</Text>
                          </Table.Td>
                        </Table.Tr>
                      );
                    },
                  )}
                </Table.Tbody>
              </Table>
            </Paper>
          )}
        </>
      )}
    </Stack>
  );
}
