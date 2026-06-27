/**
 * RecommendationsPanel — AI tavsiyalar paneli.
 *
 * - Claude-boyitilgan xulosa bo'lsa yuqorida ko'rinadi (ai_enriched=true)
 * - Tavsiyalar severity bo'yicha ranglangan kartalar:
 *   high → qizil, medium → sariq, low → ko'k
 */

import {
  Alert,
  Badge,
  Box,
  Card,
  Group,
  Stack,
  Text,
  ThemeIcon,
} from "@mantine/core";
import {
  IconAlertTriangle,
  IconAlertCircle,
  IconInfoCircle,
  IconBrain,
} from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import type { RecommendationItem, RecommendationSeverity } from "./types";

interface RecommendationsPanelProps {
  recommendations: RecommendationItem[];
  aiEnriched: boolean;
  aiSummary: string | null;
}

function severityColor(severity: RecommendationSeverity): string {
  if (severity === "high") return "red";
  if (severity === "medium") return "yellow";
  return "blue";
}

function SeverityIcon({ severity }: { severity: RecommendationSeverity }) {
  if (severity === "high")
    return (
      <ThemeIcon color="red" variant="light" size="md">
        <IconAlertTriangle size={16} />
      </ThemeIcon>
    );
  if (severity === "medium")
    return (
      <ThemeIcon color="yellow" variant="light" size="md">
        <IconAlertCircle size={16} />
      </ThemeIcon>
    );
  return (
    <ThemeIcon color="blue" variant="light" size="md">
      <IconInfoCircle size={16} />
    </ThemeIcon>
  );
}

export function RecommendationsPanel({
  recommendations,
  aiEnriched,
  aiSummary,
}: RecommendationsPanelProps) {
  const { t } = useTranslation();

  return (
    <Stack gap="sm">
      {/* Claude AI xulosasi — faqat ai_enriched=true bo'lsa */}
      {aiEnriched && aiSummary && (
        <Alert
          icon={<IconBrain size={18} />}
          color="violet"
          variant="light"
          title={t("analytics.recommendations.ai_summary_title", {
            defaultValue: "AI Xulosa (Claude)",
          })}
        >
          <Text size="sm">{aiSummary}</Text>
        </Alert>
      )}

      {recommendations.length === 0 ? (
        <Box py="md" ta="center">
          <Text c="dimmed" size="sm">
            {t("analytics.recommendations.empty", {
              defaultValue: "Hozircha tavsiyalar yo'q",
            })}
          </Text>
        </Box>
      ) : (
        recommendations.map((rec, idx) => (
          <Card
            key={`${rec.code}-${idx}`}
            withBorder
            padding="sm"
            radius="sm"
            style={{
              borderLeftWidth: 3,
              borderLeftColor: `var(--mantine-color-${severityColor(rec.severity)}-6)`,
            }}
          >
            <Group gap="sm" align="flex-start">
              <SeverityIcon severity={rec.severity} />
              <Box style={{ flex: 1 }}>
                <Group gap="xs" mb={4}>
                  <Text size="sm" fw={600}>
                    {rec.title_uz}
                  </Text>
                  <Badge
                    color={severityColor(rec.severity)}
                    variant="light"
                    size="xs"
                  >
                    {rec.severity === "high"
                      ? t("analytics.recommendations.severity_high", {
                          defaultValue: "Yuqori",
                        })
                      : rec.severity === "medium"
                        ? t("analytics.recommendations.severity_medium", {
                            defaultValue: "O'rta",
                          })
                        : t("analytics.recommendations.severity_low", {
                            defaultValue: "Past",
                          })}
                  </Badge>
                </Group>
                <Text size="sm" c="dimmed">
                  {rec.detail_uz}
                </Text>
              </Box>
            </Group>
          </Card>
        ))
      )}
    </Stack>
  );
}
