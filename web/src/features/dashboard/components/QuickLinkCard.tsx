/**
 * QuickLinkCard — tezkor havola karta komponenti.
 * Ikona + sarlavha + tavsif + navigate(to).
 */

import { Card, Group, Text, ThemeIcon, UnstyledButton } from "@mantine/core";
import { useNavigate } from "react-router-dom";

export interface QuickLinkCardProps {
  icon: React.ReactNode;
  color: string;
  label: string;
  description?: string;
  to: string;
}

export function QuickLinkCard({
  icon,
  color,
  label,
  description,
  to,
}: QuickLinkCardProps) {
  const navigate = useNavigate();

  return (
    <UnstyledButton onClick={() => navigate(to)} style={{ display: "block", width: "100%" }}>
      <Card
        shadow="xs"
        padding="md"
        radius="md"
        withBorder
        style={{ cursor: "pointer", transition: "box-shadow 0.15s ease" }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLElement).style.boxShadow =
            "0 2px 12px rgba(0,0,0,0.12)";
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLElement).style.boxShadow = "";
        }}
      >
        <Group gap="sm">
          <ThemeIcon size={32} radius="md" color={color} variant="light">
            {icon}
          </ThemeIcon>
          <div>
            <Text size="sm" fw={600}>
              {label}
            </Text>
            {description && (
              <Text size="xs" c="dimmed">
                {description}
              </Text>
            )}
          </div>
        </Group>
      </Card>
    </UnstyledButton>
  );
}
