/**
 * SuperadminLayout — superadmin uchun alohida panel qobig'i.
 *
 * Tenant AppLayout'dan butunlay alohida — superadmin
 * tenant ma'lumotlarini ko'rmaydi.
 *
 * Nav: Dashboard, Korxonalar, Foydalanuvchilar
 * Header: foydalanuvchi ismi, til, chiqish
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
  IconBuildingSkyscraper,
  IconLayoutDashboard,
  IconLogout,
  IconChevronDown,
  IconLanguage,
  IconUsers,
  IconFileText,
  IconPhoto,
} from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import { Outlet } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";

// ─── Til almashtiruvchi ───────────────────────────────────────────────────────

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

// ─── User menu ────────────────────────────────────────────────────────────────

function SuperadminUserMenu() {
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
                Superadmin
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
          onClick={() => { void handleLogout(); }}
        >
          {t("common.logout")}
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}

// ─── SuperadminLayout ─────────────────────────────────────────────────────────

export function SuperadminLayout() {
  const [mobileNavOpened, { toggle: toggleMobileNav }] = useDisclosure(false);
  const { t } = useTranslation();

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
            <Title order={4} c="violet.7">
              RETAIL <Text component="span" size="xs" c="dimmed">superadmin</Text>
            </Title>
          </Group>
          <Group gap="sm">
            <LanguageSwitcher />
            <SuperadminUserMenu />
          </Group>
        </Group>
      </AppShell.Header>

      {/* Sidebar */}
      <AppShell.Navbar p="xs">
        <ScrollArea>
          <MantineNavLink
            component={NavLink}
            to="/superadmin"
            end
            label={t("superadmin.nav.dashboard")}
            leftSection={<IconLayoutDashboard size={18} />}
            mb={2}
          />
          <MantineNavLink
            component={NavLink}
            to="/superadmin/enterprises"
            label={t("nav.enterprises")}
            leftSection={<IconBuildingSkyscraper size={18} />}
            mb={2}
          />
          <MantineNavLink
            component={NavLink}
            to="/superadmin/users"
            label={t("nav.users")}
            leftSection={<IconUsers size={18} />}
            mb={2}
          />
          <MantineNavLink
            component={NavLink}
            to="/superadmin/audit-logs"
            label={t("superadmin.nav.audit_logs")}
            leftSection={<IconFileText size={18} />}
            mb={2}
          />
          <MantineNavLink
            component={NavLink}
            to="/superadmin/banners"
            label={t("superadmin.nav.banners")}
            leftSection={<IconPhoto size={18} />}
            mb={2}
          />
        </ScrollArea>
      </AppShell.Navbar>

      {/* Kontent */}
      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
