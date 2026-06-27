/**
 * AnalyticsDashboardPage — Korxona uchun AI tahlil paneli.
 *
 * Tarkib (ADR-004):
 * - KPI kartalar (overview)
 * - Geo savdo tezligi — leaflet xarita (do'konlar velocity bo'yicha rangli)
 * - Expiry ogohlantirishlar jadvali (do'kon ombori)
 * - Mahsulot reytingi (recharts BarChart, top/bottom toggle)
 * - Shartnoma qilgan do'konlar jadvali
 * - AI tavsiyalar paneli (rule-based + ixtiyoriy Claude)
 *
 * RBAC: butun sahifa <Can permission="analytics:view"> ichida.
 * i18n: analytics.* kalitlari, defaultValue fallback.
 */

import {
  Badge,
  Box,
  Card,
  Divider,
  Group,
  Loader,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Can } from "@/rbac/Can";
import {
  useOverview,
  useContractedStores,
  useGeoVelocity,
  useExpiry,
  useProductRanking,
  useRecommendations,
} from "./api/analyticsApi";
import { GeoVelocityMap } from "./GeoVelocityMap";
import { ExpiryAlertsPanel } from "./ExpiryAlertsPanel";
import { ProductRankingChart } from "./ProductRankingChart";
import { ContractedStoresTable } from "./ContractedStoresTable";
import { RecommendationsPanel } from "./RecommendationsPanel";
import type { AnalyticsFilters, ProductOrder } from "./types";

// ─── KPI karta ────────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  color = "blue",
  badge,
}: {
  label: string;
  value: string | number;
  color?: string;
  badge?: { text: string; color: string };
}) {
  return (
    <Card withBorder padding="md" radius="sm">
      <Text size="xs" c="dimmed" mb={4}>
        {label}
      </Text>
      <Group gap="xs" align="center">
        <Text fw={700} size="xl" c={color}>
          {value}
        </Text>
        {badge && (
          <Badge color={badge.color} variant="light" size="sm">
            {badge.text}
          </Badge>
        )}
      </Group>
    </Card>
  );
}

// ─── Loading placeholder ──────────────────────────────────────────────────────

function LoadingSection() {
  const { t } = useTranslation();
  return (
    <Group justify="center" py="md">
      <Loader size="sm" />
      <Text c="dimmed">{t("common.loading")}</Text>
    </Group>
  );
}

// ─── Asosiy sahifa ─────────────────────────────────────────────────────────────

function AnalyticsDashboardContent() {
  const { t } = useTranslation();

  // Davr filtrlari
  const [fromDate, setFromDate] = useState<string>("");
  const [toDate, setToDate] = useState<string>("");
  const [expiryDays, setExpiryDays] = useState<string>("30");
  const [productOrder, setProductOrder] = useState<ProductOrder>("top");

  const filters: AnalyticsFilters = {
    from: fromDate || undefined,
    to: toDate || undefined,
  };

  const {
    data: overview,
    isLoading: overviewLoading,
    isError: overviewError,
  } = useOverview(filters);

  const {
    data: storesData,
    isLoading: storesLoading,
    isError: storesError,
  } = useContractedStores();

  const {
    data: geoData,
    isLoading: geoLoading,
    isError: geoError,
  } = useGeoVelocity(filters);

  const {
    data: expiryData,
    isLoading: expiryLoading,
    isError: expiryError,
  } = useExpiry(Number(expiryDays) || 30);

  const {
    data: productsData,
    isLoading: productsLoading,
    isError: productsError,
  } = useProductRanking(filters, productOrder, 10);

  const {
    data: recsData,
    isLoading: recsLoading,
    isError: recsError,
  } = useRecommendations();

  return (
    <Stack gap="xl">
      <Title order={3}>
        {t("analytics.title", { defaultValue: "AI Tahlil — Do'kon-Ombor Intellekti" })}
      </Title>

      {/* ─── Davr filtrlari ─── */}
      <Group gap="sm" wrap="wrap">
        <TextInput
          label={t("stats.filter.from")}
          type="date"
          value={fromDate}
          onChange={(e) => setFromDate(e.currentTarget.value)}
          w={160}
        />
        <TextInput
          label={t("stats.filter.to")}
          type="date"
          value={toDate}
          onChange={(e) => setToDate(e.currentTarget.value)}
          w={160}
        />
        <Select
          label={t("analytics.expiry.within_days_label", { defaultValue: "Expiry ogohlantirish (kun)" })}
          data={[
            { value: "7", label: "7 kun" },
            { value: "14", label: "14 kun" },
            { value: "30", label: "30 kun" },
            { value: "60", label: "60 kun" },
          ]}
          value={expiryDays}
          onChange={(v) => setExpiryDays(v ?? "30")}
          w={200}
          allowDeselect={false}
        />
      </Group>

      {/* ─── KPI kartalar ─── */}
      <Divider
        label={t("analytics.sections.overview", { defaultValue: "Umumiy ko'rsatkichlar" })}
        labelPosition="left"
      />
      {overviewLoading ? (
        <LoadingSection />
      ) : overviewError ? (
        <Text c="red">{t("errors.unknown")}</Text>
      ) : overview ? (
        <SimpleGrid cols={{ base: 2, sm: 3, md: 4 }}>
          {/* contracted_store_count — backend: OverviewOut.contracted_store_count */}
          <StatCard
            label={t("analytics.overview.contracted_stores", { defaultValue: "Shartnoma do'konlar" })}
            value={(overview.contracted_store_count ?? 0).toLocaleString()}
            color="blue"
          />
          {/* contract_status.active — backend: OverviewOut.contract_status.active */}
          <StatCard
            label={t("analytics.overview.active_contracts", { defaultValue: "Faol shartnomalar" })}
            value={(overview.contract_status?.active ?? 0).toLocaleString()}
            color="green"
          />
          {/* contract_status.expiring — backend: OverviewOut.contract_status.expiring */}
          <StatCard
            label={t("analytics.overview.expiring_contracts", { defaultValue: "Tugayotgan" })}
            value={(overview.contract_status?.expiring ?? 0).toLocaleString()}
            color="yellow.7"
            badge={
              (overview.contract_status?.expiring ?? 0) > 0
                ? { text: "!", color: "yellow" }
                : undefined
            }
          />
          {/* contract_status.expired — backend: OverviewOut.contract_status.expired */}
          <StatCard
            label={t("analytics.overview.expired_contracts", { defaultValue: "Muddati o'tgan" })}
            value={(overview.contract_status?.expired ?? 0).toLocaleString()}
            color="red"
          />
          {/* sold_qty_total — backend: OverviewOut.sold_qty_total */}
          <StatCard
            label={t("analytics.overview.total_sold_qty", { defaultValue: "Sotilgan (dona)" })}
            value={(overview.sold_qty_total ?? 0).toLocaleString()}
            color="teal"
          />
          {/* revenue_total — backend: OverviewOut.revenue_total */}
          <StatCard
            label={t("analytics.overview.total_revenue", { defaultValue: "Daromad (UZS)" })}
            value={Number(overview.revenue_total ?? 0).toLocaleString()}
            color="teal"
          />
          {/* expiry_risk_count — backend: OverviewOut.expiry_risk_count */}
          <StatCard
            label={t("analytics.overview.expiry_risk_sku", { defaultValue: "Expiry-risk SKU" })}
            value={(overview.expiry_risk_count ?? 0).toLocaleString()}
            color={(overview.expiry_risk_count ?? 0) > 0 ? "red" : "gray"}
            badge={
              (overview.expiry_risk_count ?? 0) > 0
                ? {
                    text: t("analytics.overview.urgent", { defaultValue: "Shoshilinch" }),
                    color: "red",
                  }
                : undefined
            }
          />
        </SimpleGrid>
      ) : (
        <Box py="md" ta="center">
          <Text c="dimmed" size="sm">
            {t("analytics.overview.empty", { defaultValue: "Ma'lumot yo'q" })}
          </Text>
        </Box>
      )}

      {/* ─── Geo savdo tezligi ─── */}
      <Divider
        label={t("analytics.sections.geo_velocity", { defaultValue: "Geo savdo tezligi" })}
        labelPosition="left"
      />
      {geoLoading ? (
        <LoadingSection />
      ) : geoError ? (
        <Text c="red">{t("errors.unknown")}</Text>
      ) : geoData ? (
        <Card withBorder padding="md">
          <Text fw={500} mb="sm" size="sm">
            {t("analytics.geo.map_title", {
              defaultValue: "Savdo tezligi xaritasi (qizil=tez, sariq=o'rta, ko'k=past)",
            })}
          </Text>
          {/* geoData.items — backend: GeoVelocityOut.items */}
          <GeoVelocityMap stores={geoData.items ?? []} />
          {(geoData.period_days ?? 0) > 0 && (
            <Text size="xs" c="dimmed" mt="xs">
              {t("analytics.geo.period_note", {
                defaultValue: "Davr: {{days}} kun",
                days: geoData.period_days,
              })}
            </Text>
          )}
        </Card>
      ) : null}

      {/* ─── Expiry ogohlantirishlar ─── */}
      <Divider
        label={t("analytics.sections.expiry", { defaultValue: "Muddati o'tayotgan tovarlar" })}
        labelPosition="left"
      />
      {expiryLoading ? (
        <LoadingSection />
      ) : expiryError ? (
        <Text c="red">{t("errors.unknown")}</Text>
      ) : expiryData ? (
        <ExpiryAlertsPanel items={expiryData.items ?? []} />
      ) : null}

      {/* ─── Mahsulot reytingi ─── */}
      <Divider
        label={t("analytics.sections.products", { defaultValue: "Mahsulot reytingi" })}
        labelPosition="left"
      />
      {productsLoading ? (
        <LoadingSection />
      ) : productsError ? (
        <Text c="red">{t("errors.unknown")}</Text>
      ) : productsData ? (
        <Card withBorder padding="md">
          {/* productsData.items — backend: ProductRankingOut.items */}
          <ProductRankingChart
            products={productsData.items ?? []}
            order={productOrder}
            onOrderChange={setProductOrder}
          />
        </Card>
      ) : null}

      {/* ─── Shartnoma qilgan do'konlar ─── */}
      <Divider
        label={t("analytics.sections.stores", { defaultValue: "Shartnoma do'konlar" })}
        labelPosition="left"
      />
      {storesLoading ? (
        <LoadingSection />
      ) : storesError ? (
        <Text c="red">{t("errors.unknown")}</Text>
      ) : storesData ? (
        <ContractedStoresTable stores={storesData.stores ?? []} />
      ) : null}

      {/* ─── AI tavsiyalar ─── */}
      <Divider
        label={t("analytics.sections.recommendations", { defaultValue: "AI Tavsiyalar" })}
        labelPosition="left"
      />
      {recsLoading ? (
        <LoadingSection />
      ) : recsError ? (
        <Text c="red">{t("errors.unknown")}</Text>
      ) : recsData ? (
        <RecommendationsPanel
          recommendations={recsData.recommendations ?? []}
          aiEnabled={recsData.ai_enabled ?? false}
          aiSummary={recsData.ai_summary ?? null}
        />
      ) : null}
    </Stack>
  );
}

// ─── Sahifa (RBAC wrapper) ─────────────────────────────────────────────────────

export function AnalyticsDashboardPage() {
  const { t } = useTranslation();

  return (
    <Can
      permission="analytics:view"
      fallback={
        <Box py="xl" ta="center">
          <Text c="dimmed">
            {t("analytics.access_denied", { defaultValue: "Bu sahifani ko'rish uchun ruxsat yo'q" })}
          </Text>
        </Box>
      }
    >
      <AnalyticsDashboardContent />
    </Can>
  );
}
