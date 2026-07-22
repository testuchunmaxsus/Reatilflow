/**
 * ErrorBoundary — ilova ildizidagi umumiy xato ushlagich.
 *
 * FIX #39: root darajasida ErrorBoundary yo'q edi — render vaqtidagi
 * kutilmagan xato (masalan lazy-chunk import xatosi Suspense ichida qayta
 * uloqtirilganda) butun ilovani oq sahifaga aylantirar edi. Bu komponent
 * xatoni ushlab, foydalanuvchiga tushunarli fallback UI va "Sahifani
 * yangilash" tugmasini ko'rsatadi.
 */

import { Component } from "react";
import type { ReactNode } from "react";
import { Button, Center, Stack, Text, Title } from "@mantine/core";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  override componentDidCatch(error: unknown) {
    // eslint-disable-next-line no-console
    console.error("Ilova xatosi (ErrorBoundary):", error);
  }

  override render() {
    if (this.state.hasError) {
      return (
        <Center h="100vh">
          <Stack align="center" gap="sm">
            <Title order={3}>Nimadir xato ketdi</Title>
            <Text c="dimmed" size="sm" ta="center">
              Sahifani yuklashda kutilmagan xato yuz berdi. Sahifani
              yangilab ko'ring.
            </Text>
            <Button onClick={() => window.location.reload()}>
              Sahifani yangilash
            </Button>
          </Stack>
        </Center>
      );
    }
    return this.props.children;
  }
}
