/**
 * RoleDashboard — "/" bosh sahifasi uchun rol-dispatcher.
 *
 * user.role bo'yicha tegishli dashboard komponentini render qiladi:
 *   administrator → AdminDashboard
 *   accountant    → AccountantDashboard
 *   agent         → AgentDashboard
 *   store         → StoreDashboard
 *   courier       → CourierDashboardPage (mavjud, qayta ishlatiladi)
 *   fallback      → DashboardPage (xavfsiz)
 */

import { Center, Loader } from "@mantine/core";
import { Suspense, lazy } from "react";
import { useAuth } from "@/auth/AuthContext";
import { DashboardPage } from "@/pages/DashboardPage";
import { AdminDashboard } from "./AdminDashboard";
import { AccountantDashboard } from "./AccountantDashboard";
import { AgentDashboard } from "./AgentDashboard";
import { StoreDashboard } from "./StoreDashboard";

// Courier dashboard — mavjud komponent (lazy, chunki kod-split allaqachon u yerda)
const CourierDashboardPage = lazy(() =>
  import("@/features/delivery/CourierDashboardPage").then((m) => ({
    default: m.CourierDashboardPage,
  }))
);

const FallbackLoader = (
  <Center py="xl">
    <Loader size="md" />
  </Center>
);

export function RoleDashboard() {
  const { user } = useAuth();

  switch (user?.role) {
    case "administrator":
      return <AdminDashboard />;
    case "accountant":
      return <AccountantDashboard />;
    case "agent":
      return <AgentDashboard />;
    case "store":
      return <StoreDashboard />;
    case "courier":
      return (
        <Suspense fallback={FallbackLoader}>
          <CourierDashboardPage />
        </Suspense>
      );
    default:
      // superadmin AppLayout'dan /superadmin'ga redirect bo'ladi — bu yerga yetmaydi
      // noma'lum rol uchun xavfsiz fallback
      return <DashboardPage />;
  }
}
