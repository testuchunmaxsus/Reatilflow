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
          <StatCard
            label={t("analytics.overview.contracted_stores", { defaultValue: "Shartnoma do'konlar" })}
            value={overview.contracted_stores_count}
            color="blue"
          />
          <StatCard
            label={t("analytics.overview.active_contracts", { defaultValue: "Faol shartnomalar" })}
            value={overview.active_contracts}
            color="green"
          />
          <StatCard
            label={t("analytics.overview.expiring_contracts", { defaultValue: "Tugayotgan" })}
            value={overview.expiring_contracts}
            color="yellow.7"
            badge={overview.expiring_contracts > 0 ? { text: "!", color: "yellow" } : undefined}
          />
          <StatCard
            label={t("analytics.overview.expired_contracts", { defaultValue: "Muddati o'tgan" })}
            value={overview.expired_contracts}
            color="red"
          />
          <StatCard
            label={t("analytics.overview.total_sold_qty", { defaultValue: "Sotilgan (dona)" })}
            value={overview.total_sold_qty.toLocaleString()}
            color="teal"
          />
          <StatCard
            label={t("analytics.overview.total_revenue", { defaultValue: "Daromad (UZS)" })}
            value={Number(overview.total_revenue).toLocaleString()}
            color="teal"
          />
          <StatCard
            label={t("analytics.overview.expiry_risk_sku", { defaultValue: "Expiry-risk SKU" })}
            value={overview.expiry_risk_sku_count}
            color={overview.expiry_risk_sku_count > 0 ? "red" : "gray"}
            badge={
              overview.expiry_risk_sku_count > 0
                ? { text: t("analytics.overview.urgent", { defaultValue: "Shoshilinch" }), color: "red" }
                : undefined
            }
          />
          {overview.top_product_name && (
            <StatCard
              label={t("analytics.overview.top_product", { defaultValue: "Eng ko'p sotiladigan" })}
              value={overview.top_product_name}
              color="violet"
            />
          )}
        </SimpleGrid>
      ) : null}

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
          <GeoVelocityMap stores={geoData.stores} />
          {geoData.period_days > 0 && (
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
        <ExpiryAlertsPanel items={expiryData.items} />
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
          <ProductRankingChart
            products={productsData.products}
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
        <ContractedStoresTable stores={storesData.stores} />
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
          recommendations={recsData.recommendations}
          aiEnriched={recsData.ai_enriched}
          aiSummary={recsData.ai_summary}
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
