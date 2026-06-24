/**
 * RETAIL Veb SPA — kirish nuqtasi
 *
 * Stek:
 * - React 18 + ReactDOM.createRoot
 * - Mantine UI (MantineProvider + Notifications)
 * - TanStack Query (server state boshqaruvi)
 * - React Router (yo'naltirish)
 * - i18next (uz/ru lokalizatsiya)
 * - AuthProvider (JWT + refresh oqimi)
 */

import { StrictMode, lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { MantineProvider, createTheme, Center, Loader } from "@mantine/core";
import { Notifications } from "@mantine/notifications";

// i18n — import before App (yuklash va konfiguratsiya)
import "@/i18n";

// Mantine CSS (zarur)
import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import "@mantine/dates/styles.css";

import { AuthProvider } from "@/auth/AuthContext";
import { ProtectedRoute } from "@/auth/ProtectedRoute";
import { LoginPage } from "@/auth/LoginPage";
import { AppLayout } from "@/layouts/AppLayout";
import { EnterpriseProvider } from "@/enterprise/EnterpriseContext";
import { DashboardPage } from "@/pages/DashboardPage";
import { CatalogListPage } from "@/features/catalog/CatalogListPage";
import { CustomerListPage } from "@/features/customers/CustomerListPage";
import { OrderListPage } from "@/features/orders/OrderListPage";
// Stats sahifasi — recharts bilan lazy yuklash (code-split)
const StatsDashboardPage = lazy(() =>
  import("@/features/stats/StatsDashboardPage").then((m) => ({
    default: m.StatsDashboardPage,
  })),
);
import { UsersListPage } from "@/features/users/UsersListPage";
import { RolePermissionsPage } from "@/features/rbac/RolePermissionsPage";
import { ContractsListPage } from "@/features/contracts/ContractsListPage";
import { TicketsListPage } from "@/features/tickets/TicketsListPage";
import { PromoListPage } from "@/features/promo/PromoListPage";
// Superadmin panel — code-split
const SuperadminLayout = lazy(() =>
  import("@/features/superadmin/SuperadminLayout").then((m) => ({
    default: m.SuperadminLayout,
  })),
);
const SuperadminDashboardPage = lazy(() =>
  import("@/features/superadmin/SuperadminDashboardPage").then((m) => ({
    default: m.SuperadminDashboardPage,
  })),
);
const SuperadminEnterprisesPage = lazy(() =>
  import("@/features/superadmin/SuperadminEnterprisesPage").then((m) => ({
    default: m.SuperadminEnterprisesPage,
  })),
);
const SuperadminEnterpriseDetailPage = lazy(() =>
  import("@/features/superadmin/SuperadminEnterpriseDetailPage").then((m) => ({
    default: m.SuperadminEnterpriseDetailPage,
  })),
);
const SuperadminUsersPage = lazy(() =>
  import("@/features/superadmin/SuperadminUsersPage").then((m) => ({
    default: m.SuperadminUsersPage,
  })),
);
// Enterprise settings
import { EnterpriseSettingsPage } from "@/features/enterprise-settings/EnterpriseSettingsPage";
// Marketplace
import { MarketplaceLayout } from "@/features/marketplace/MarketplaceLayout";
import { IncomingOrdersPage } from "@/features/marketplace/IncomingOrdersPage";
import { OutgoingOrdersPage } from "@/features/marketplace/OutgoingOrdersPage";
import { BannersPage } from "@/features/marketplace/BannersPage";

// ─── TanStack Query ───────────────────────────────────────────────────────

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 daqiqa
      retry: (failureCount, error) => {
        // 401/403 xatolarida qayta urinmaymiz
        if (
          error instanceof Error &&
          error.message.includes("401") ||
          error instanceof Error &&
          error.message.includes("403")
        ) {
          return false;
        }
        return failureCount < 2;
      },
    },
  },
});

// ─── Mantine tema ─────────────────────────────────────────────────────────

const theme = createTheme({
  fontFamily: "Inter, system-ui, -apple-system, sans-serif",
  primaryColor: "blue",
  defaultRadius: "sm",
  components: {
    NavLink: {
      styles: {
        root: {
          borderRadius: "var(--mantine-radius-sm)",
        },
      },
    },
  },
});

// ─── Ilova ────────────────────────────────────────────────────────────────

function App() {
  return (
    <MantineProvider theme={theme}>
      <Notifications position="top-right" />
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <EnterpriseProvider>
            <BrowserRouter>
              <Routes>
                {/* Ochiq sahifalar */}
                <Route path="/login" element={<LoginPage />} />

                {/* Superadmin panel — alohida layout */}
                <Route element={<ProtectedRoute requiredRole="superadmin" />}>
                  <Route
                    path="/superadmin"
                    element={
                      <Suspense fallback={<Center h="100vh"><Loader size="lg" /></Center>}>
                        <SuperadminLayout />
                      </Suspense>
                    }
                  >
                    {/* Dashboard — index sahifa */}
                    <Route
                      index
                      element={
                        <Suspense fallback={<Center py="xl"><Loader size="md" /></Center>}>
                          <SuperadminDashboardPage />
                        </Suspense>
                      }
                    />
                    {/* Korxonalar ro'yxati */}
                    <Route
                      path="enterprises"
                      element={
                        <Suspense fallback={<Center py="xl"><Loader size="md" /></Center>}>
                          <SuperadminEnterprisesPage />
                        </Suspense>
                      }
                    />
                    {/* Korxona tafsiloti */}
                    <Route
                      path="enterprises/:id"
                      element={
                        <Suspense fallback={<Center py="xl"><Loader size="md" /></Center>}>
                          <SuperadminEnterpriseDetailPage />
                        </Suspense>
                      }
                    />
                    {/* Cross-tenant foydalanuvchilar */}
                    <Route
                      path="users"
                      element={
                        <Suspense fallback={<Center py="xl"><Loader size="md" /></Center>}>
                          <SuperadminUsersPage />
                        </Suspense>
                      }
                    />
                    <Route path="*" element={<Navigate to="/superadmin" replace />} />
                  </Route>
                </Route>

                {/* Himoyalangan sahifalar — tenant foydalanuvchilar */}
                <Route element={<ProtectedRoute />}>
                  <Route element={<AppLayout />}>
                    <Route index element={<DashboardPage />} />
                    <Route path="catalog" element={<CatalogListPage />} />
                    <Route path="customers" element={<CustomerListPage />} />
                    <Route path="orders" element={<OrderListPage />} />
                    <Route
                      path="stats"
                      element={
                        <Suspense
                          fallback={
                            <Center py="xl">
                              <Loader size="md" />
                            </Center>
                          }
                        >
                          <StatsDashboardPage />
                        </Suspense>
                      }
                    />
                    {/* /users — foydalanuvchilar boshqaruvi */}
                    <Route path="users" element={<UsersListPage />} />
                    <Route path="rbac" element={<RolePermissionsPage />} />
                    {/* /contracts — shartnomalar boshqaruvi */}
                    <Route path="contracts" element={<ContractsListPage />} />
                    {/* /tickets — murojaatlar boshqaruvi */}
                    <Route path="tickets" element={<TicketsListPage />} />
                    {/* /promo — aksiyalar boshqaruvi */}
                    <Route path="promo" element={<PromoListPage />} />
                    {/* /marketplace — marketplace boshqaruvi */}
                    <Route path="marketplace" element={<MarketplaceLayout />}>
                      <Route index element={<IncomingOrdersPage />} />
                      <Route path="outgoing" element={<OutgoingOrdersPage />} />
                      <Route path="banners" element={<BannersPage />} />
                    </Route>
                    {/* /settings — korxona modullari sozlamalari */}
                    <Route path="settings" element={<EnterpriseSettingsPage />} />
                    {/* Noma'lum yo'l — bosh sahifaga */}
                    <Route path="*" element={<Navigate to="/" replace />} />
                  </Route>
                </Route>

                {/* Login sahifasiga fallback */}
                <Route path="*" element={<Navigate to="/login" replace />} />
              </Routes>
            </BrowserRouter>
          </EnterpriseProvider>
        </AuthProvider>
        {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
      </QueryClientProvider>
    </MantineProvider>
  );
}

// ─── DOM mount ────────────────────────────────────────────────────────────

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element #root topilmadi");
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
