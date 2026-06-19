/**
 * PlaceholderPage — T8 da to'ldirilishi kerak bo'lgan sahifalar uchun.
 */

import { Box, Text, ThemeIcon, Title } from "@mantine/core";
import { IconClock } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";

interface PlaceholderPageProps {
  titleKey: string;
  descriptionKey?: string;
}

export function PlaceholderPage({ titleKey, descriptionKey }: PlaceholderPageProps) {
  const { t } = useTranslation();

  return (
    <Box ta="center" py={80}>
      <ThemeIcon size={64} radius="xl" variant="light" color="blue" mb="md" mx="auto">
        <IconClock size={32} />
      </ThemeIcon>
      <Title order={3} mb="xs">
        {t(titleKey)}
      </Title>
      {descriptionKey && (
        <Text c="dimmed" mb="md">
          {t(descriptionKey)}
        </Text>
      )}
      <Text size="lg" c="blue">
        {t("common.coming_soon")}
      </Text>
    </Box>
  );
}
