/**
 * GeoVelocityMap — Leaflet xaritasi: do'kon markerlar, marker o'lchami/rangi velocity bo'yicha.
 *
 * Marker rangi:
 *   - velocity yuqori (top kvartil) → qizil
 *   - velocity o'rta (2-3 kvartil)  → to'q sariq
 *   - velocity past                 → ko'k
 *
 * Popup: do'kon nomi + sotilgan qty + revenue + velocity/kun.
 */

import "leaflet/dist/leaflet.css";

import L from "leaflet";
import { MapContainer, TileLayer, CircleMarker, Popup } from "react-leaflet";
import { Box, Text } from "@mantine/core";
import type { GeoVelocityItem } from "./types";

// Leaflet default icon tuzatish (Vite PNG yo'llari muammosi)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: new URL("leaflet/dist/images/marker-icon-2x.png", import.meta.url).href,
  iconUrl: new URL("leaflet/dist/images/marker-icon.png", import.meta.url).href,
  shadowUrl: new URL("leaflet/dist/images/marker-shadow.png", import.meta.url).href,
});

const DEFAULT_CENTER: [number, number] = [40.3842, 71.7843]; // Farg'ona
const DEFAULT_ZOOM = 10;

interface GeoVelocityMapProps {
  stores: GeoVelocityItem[];
}

function getMarkerColor(velocity: number, maxVelocity: number): string {
  if (maxVelocity === 0) return "#339af0";
  const ratio = velocity / maxVelocity;
  if (ratio >= 0.66) return "#fa5252"; // yuqori — qizil
  if (ratio >= 0.33) return "#fab005"; // o'rta — sariq
  return "#339af0"; // past — ko'k
}

function getMarkerRadius(velocity: number, maxVelocity: number): number {
  if (maxVelocity === 0) return 8;
  const ratio = velocity / maxVelocity;
  return 6 + ratio * 14; // 6 dan 20 gacha
}

export function GeoVelocityMap({ stores }: GeoVelocityMapProps) {
  const withGps = stores.filter((s) => s.lat !== null && s.lng !== null);
  const maxVelocity = Math.max(...withGps.map((s) => s.velocity_per_day), 0);

  // Xarita markazini birinchi nuqtaga qarab hisoblash
  const center: [number, number] =
    withGps.length > 0
      ? [withGps[0].lat as number, withGps[0].lng as number]
      : DEFAULT_CENTER;

  if (withGps.length === 0) {
    return (
      <Box py="md" ta="center">
        <Text c="dimmed" size="sm">
          GPS koordinatalari bo'lgan do'konlar topilmadi
        </Text>
      </Box>
    );
  }

  return (
    <MapContainer
      center={center}
      zoom={DEFAULT_ZOOM}
      style={{ height: 360, width: "100%", borderRadius: 8 }}
    >
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
      />
      {withGps.map((store) => (
        <CircleMarker
          key={store.store_id}
          center={[store.lat as number, store.lng as number]}
          radius={getMarkerRadius(store.velocity_per_day, maxVelocity)}
          pathOptions={{
            color: getMarkerColor(store.velocity_per_day, maxVelocity),
            fillColor: getMarkerColor(store.velocity_per_day, maxVelocity),
            fillOpacity: 0.75,
          }}
        >
          <Popup>
            <div style={{ minWidth: 180 }}>
              <strong>{store.store_name}</strong>
              {store.address && (
                <div style={{ fontSize: 12, color: "#666", marginTop: 2 }}>
                  {store.address}
                </div>
              )}
              <div style={{ marginTop: 6, fontSize: 13 }}>
                <div>Sotilgan: <strong>{store.sold_qty}</strong> dona</div>
                <div>Daromad: <strong>{Number(store.revenue).toLocaleString()} UZS</strong></div>
                <div>
                  Tezlik: <strong>{store.velocity_per_day.toFixed(1)}</strong> dona/kun
                </div>
              </div>
            </div>
          </Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
