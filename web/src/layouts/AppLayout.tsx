/**
 * AppLayout — asosiy ilova qobig'i (Mantine AppShell).
 *
 * Tarkib:
 * - Sidebar navigatsiya (ruxsatga qarab filtrlangan)
 * - Header: foydalanuvchi nomi, til almashtirish, logout
 *
 * Nav elementlari RBAC.md §3.6 ga ko'ra ruxsatlarni tekshiradi.
 */

import { NavLink, useNavigate } from "react-router-dom";
import {
  AppShell,
  Box,
  Burger,
  Group,
  Menu,
  NavLink as MantineNavLink,
  ScrollArea,
  Select,
  Text,
  Title,
  UnstyledButton,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import {
  IconChartBar,
  IconHome,
  IconPackage,
  IconShoppingCart,
  IconBuildingStore,
  IconUsers,
  IconShieldLock,
  IconLogout,
  IconChevronDown,
  IconLanguage,
  IconFileText,
  IconMessage,
  IconTag,
  IconSettings,
} from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import { Outlet } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { usePermissions } from "@/rbac/usePermissions";
import { useEnterprise } from "@/enterprise/EnterpriseContext";
import type { UserRole } from "@/api/types";

// ─── Nav elementlari ─────────────────────────────────────────────────────

interface NavItem {
  label: string;
  path: string;
  icon: React.ComponentType<{ size?: number | string }>;
  /** Agar undefined bo'lsa — barcha foydalanuvchilar ko'radi */
  requiredPermission?: string;
  /** Modul kaliti — yoqilmagan bo'lsa nav elementini yashiradi */
  requiredModule?: string;
}

function useNavItems(): NavItem[] {
  const { t } = useTranslation();

  return [
    {
      label: t("nav.dashboard"),
      path: "/",
      icon: IconHome,
    },
    {
      label: t("nav.catalog"),
      path: "/catalog",
      icon: IconPackage,
      requiredPermission: "catalog:view",
      requiredModule: "catalog",
    },
    {
      label: t("nav.customers"),
      path: "/customers",
      icon: IconBuildingStore,
      requiredPermission: "customers:view",
      requiredModule: "customers",
    },
    {
      label: t("nav.orders"),
      path: "/orders",
      icon: IconShoppingCart,
      requiredPermission: "catalog:view",
      requiredModule: "orders",
    },
    {
      label: t("nav.stats"),
      path: "/stats",
      icon: IconChartBar,
      requiredPermission: "stats:view",
      requiredModule: "stats",
    },
    {
      label: t("nav.users"),
      path: "/users",
      icon: IconUsers,
      requiredPermission: "rbac:view",
    },
    {
      label: t("nav.rbac"),
      path: "/rbac",
      icon: IconShieldLock,
      requiredPermission: "rbac:create",
    },
    {
      label: t("nav.contracts"),
      path: "/contracts",
      icon: IconFileText,
      requiredPermission: "contracts:view",
      requiredModule: "contracts",
    },
    {
      label: t("nav.tickets"),
      path: "/tickets",
      icon: IconMessage,
      requiredPermission: "tickets:view",
      requiredModule: "tickets",
    },
    {
      label: t("nav.promo"),
      path: "/promo",
      icon: IconTag,
      requiredPermission: "promo:view",
      requiredModule: "promo",
    },
    {
      label: t("nav.settings"),
      path: "/settings",
      icon: IconSettings,
      requiredPermission: "rbac:view",
    },
  ];
}

// ─── Til almashtiruvchi ───────────────────────────────────────────────────

function LanguageSwitcher() {
  const { i18n, t } = useTranslation();
  return (
    <Select
      size="xs"
      w={80}
      value={i18n.language}
      onChange={(val) => val && i18n.changeLanguage(val)}
      data={[
        { value: "uz", label: "UZ" },
        { value: "ru", label: "RU" },
      ]}
      leftSection={<IconLanguage size={14} />}
      aria-label={t("common.language")}
      allowDeselect={false}
      comboboxProps={{ width: 100, position: "bottom-end" }}
    />
  );
}

// ─── User menu ────────────────────────────────────────────────────────────

function UserMenu({ role }: { role: UserRole }) {
  const { user, logout } = useAuth();
  const { t } = useTranslation();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <Menu shadow="md" width={200}>
      <Menu.Target>
        <UnstyledButton>
          <Group gap="xs">
            <Box>
              <Text size="sm" fw={500} lh={1}>
                {user?.full_name}
              </Text>
              <Text size="xs" c="dimmed">
                {t(`common.role.${role}`)}
              </Text>
            </Box>
            <IconChevronDown size={14} />
          </Group>
        </UnstyledButton>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Item
          leftSection={<IconLogout size={14} />}
          c="red"
          onClick={handleLogout}
        >
          {t("common.logout")}
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}

// ─── AppLayout ───────────────────────────────────────────────────────────

export function AppLayout() {
  const [mobileNavOpened, { toggle: toggleMobileNav }] = useDisclosure(false);
  const { user } = useAuth();
  const { can } = usePermissions();
  const { hasModule } = useEnterprise();
  const navItems = useNavItems();

  const visibleItems = navItems.filter((item) => {
    // RBAC ruxsat tekshiruvi
    if (item.requiredPermission && !can(item.requiredPermission)) return false;
    // Modul gating tekshiruvi
    if (item.requiredModule && !hasModule(item.requiredModule)) return false;
    return true;
  });

  return (
    <AppShell
      header={{ height: 56 }}
      navbar={{
        width: 240,
        breakpoint: "sm",
        collapsed: { mobile: !mobileNavOpened },
      }}
      padding="md"
    >
      {/* Header */}
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group>
            <Burger
              opened={mobileNavOpened}
              onClick={toggleMobileNav}
              hiddenFrom="sm"
              size="sm"
            />
            <Title order={4} c="blue.7">
              RETAIL
            </Title>
          </Group>
          <Group gap="sm">
            <LanguageSwitcher />
            {user && <UserMenu role={user.role} />}
          </Group>
        </Group>
      </AppShell.Header>

      {/* Sidebar */}
      <AppShell.Navbar p="xs">
        <ScrollArea>
          {visibleItems.map((item) => (
            <MantineNavLink
              key={item.path}
              component={NavLink}
              to={item.path}
              end={item.path === "/"}
              label={item.label}
              leftSection={<item.icon size={18} />}
              mb={2}
            />
          ))}
        </ScrollArea>
      </AppShell.Navbar>

      {/* Kontent */}
      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
