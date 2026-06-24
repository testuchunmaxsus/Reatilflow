/**
 * RolePermissionsPage — ruxsatlar matritsasi sahifasi.
 *
 * Rol × Modul × Amal jadval ko'rinishida (frontend statik matritsa).
 *
 * Backend'da faqat GET /rbac/my-permissions va GET /rbac/check endpointlari
 * mavjud — umumiy rol matritsasini qaytaruvchi endpoint yo'q.
 * Shuning uchun frontend ROLE_PERMISSIONS matritsasini to'g'ridan-to'g'ri
 * import qilish o'rniga, usePermissions() logikasiga asoslangan statik ma'lumot
 * ishlatiladi (backend permissions.py bilan sinxron).
 *
 * Faqat <Can permission="rbac:view"> — administrator ko'radi.
 */

import {
  Badge,
  Box,
  Center,
  Group,
  ScrollArea,
  Table,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { IconCheck, IconX, IconShieldLock } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import { Can } from "@/rbac/Can";

// ─── Statik matritsa (backend permissions.py ga mos) ────────────────────────
//
// Backend endpoint mavjud emas (faqat /my-permissions va /check).
// Matritsa backend ROLE_PERMISSIONS dan olingan (sinxron qo'lda saqlangan).
// Agar matritsa o'zgarsa — backend/app/modules/rbac/permissions.py ham yangilanishi kerak.

type RoleName = "administrator" | "accountant" | "agent" | "courier" | "store";
type ActionName = "view" | "create" | "edit" | "delete" | "approve";

interface ModulePermissions {
  module: string;
  labelKey: string;
  permissions: Record<RoleName, Set<ActionName>>;
}

const ROLES: RoleName[] = ["administrator", "accountant", "agent", "courier", "store"];
const ACTIONS: ActionName[] = ["view", "create", "edit", "delete", "approve"];

// Rollar uchun rang
const ROLE_COLORS: Record<RoleName, string> = {
  administrator: "red",
  accountant: "violet",
  agent: "blue",
  courier: "teal",
  store: "orange",
};

// Matritsa ma'lumotlari (backend permissions.py §3.6 ga mos)
// Module.* barcha qiymatlar: catalog, agent_cabinet, attendance, delivery, stock,
// finance, tickets, customers, stats, contracts, promo, rbac, orders, gps, pos, marketplace
const MATRIX: ModulePermissions[] = [
  {
    module: "catalog",
    labelKey: "rbac.matrix.modules.catalog",
    permissions: {
      administrator: new Set(["view", "create", "edit", "delete"]),
      accountant:    new Set(["view"]),
      agent:         new Set(["view"]),
      courier:       new Set(["view"]),
      store:         new Set(["view"]),
    },
  },
  {
    module: "customers",
    labelKey: "rbac.matrix.modules.customers",
    permissions: {
      administrator: new Set(["view", "create", "edit", "delete"]),
      accountant:    new Set(["view"]),
      agent:         new Set(["view", "edit"]),
      courier:       new Set(["view"]),
      store:         new Set(["view", "edit"]),
    },
  },
  {
    module: "orders",
    labelKey: "rbac.matrix.modules.orders",
    permissions: {
      administrator: new Set(["view", "create", "edit"]),
      accountant:    new Set(["view"]),
      agent:         new Set(["view", "create", "edit"]),
      courier:       new Set([]),
      store:         new Set(["view"]),
    },
  },
  {
    module: "stats",
    labelKey: "rbac.matrix.modules.stats",
    permissions: {
      administrator: new Set(["view"]),
      accountant:    new Set(["view"]),
      agent:         new Set(["view"]),
      courier:       new Set(["view"]),
      store:         new Set(["view"]),
    },
  },
  {
    module: "finance",
    labelKey: "rbac.matrix.modules.finance",
    permissions: {
      administrator: new Set(["view"]),
      accountant:    new Set(["view", "create", "edit", "delete", "approve"]),
      agent:         new Set(["view"]),
      courier:       new Set([]),
      store:         new Set(["view"]),
    },
  },
  {
    module: "delivery",
    labelKey: "rbac.matrix.modules.delivery",
    permissions: {
      administrator: new Set(["view", "create", "edit"]),
      accountant:    new Set(["view"]),
      agent:         new Set(["view", "create"]),
      courier:       new Set(["view", "edit"]),
      store:         new Set(["view"]),
    },
  },
  {
    module: "stock",
    labelKey: "rbac.matrix.modules.stock",
    permissions: {
      administrator: new Set(["view", "create", "edit", "delete"]),
      accountant:    new Set(["view"]),
      agent:         new Set(["view"]),
      courier:       new Set(["view"]),
      store:         new Set([]),
    },
  },
  {
    module: "tickets",
    labelKey: "rbac.matrix.modules.tickets",
    permissions: {
      administrator: new Set(["view", "edit"]),
      accountant:    new Set(["view", "edit"]),
      agent:         new Set(["view", "create"]),
      courier:       new Set(["view", "create"]),
      store:         new Set(["view", "create"]),
    },
  },
  {
    module: "contracts",
    labelKey: "rbac.matrix.modules.contracts",
    permissions: {
      administrator: new Set(["view", "create", "edit", "delete"]),
      accountant:    new Set(["view", "edit"]),
      agent:         new Set(["view"]),
      courier:       new Set([]),
      store:         new Set(["view"]),
    },
  },
  {
    module: "promo",
    labelKey: "rbac.matrix.modules.promo",
    permissions: {
      administrator: new Set(["view", "create", "edit", "delete"]),
      accountant:    new Set(["view"]),
      agent:         new Set(["view"]),
      courier:       new Set([]),
      store:         new Set(["view"]),
    },
  },
  {
    module: "attendance",
    labelKey: "rbac.matrix.modules.attendance",
    permissions: {
      administrator: new Set(["view"]),
      accountant:    new Set(["view"]),
      agent:         new Set(["view", "create"]),
      courier:       new Set(["view", "create"]),
      store:         new Set([]),
    },
  },
  {
    module: "agent_cabinet",
    labelKey: "rbac.matrix.modules.agent_cabinet",
    permissions: {
      administrator: new Set(["view"]),
      accountant:    new Set(["view"]),
      agent:         new Set(["view", "edit"]),
      courier:       new Set([]),
      store:         new Set([]),
    },
  },
  {
    module: "gps",
    labelKey: "rbac.matrix.modules.gps",
    permissions: {
      administrator: new Set(["view"]),
      accountant:    new Set([]),
      agent:         new Set(["view", "create"]),
      courier:       new Set(["view", "create"]),
      store:         new Set([]),
    },
  },
  {
    module: "pos",
    labelKey: "rbac.matrix.modules.pos",
    permissions: {
      administrator: new Set(["view", "create"]),
      accountant:    new Set(["view"]),
      agent:         new Set([]),
      courier:       new Set([]),
      store:         new Set(["view", "create"]),
    },
  },
  {
    module: "marketplace",
    labelKey: "rbac.matrix.modules.marketplace",
    permissions: {
      administrator: new Set(["view", "create", "edit"]),
      accountant:    new Set(["view", "create", "edit"]),
      agent:         new Set(["view", "create"]),
      courier:       new Set(["view", "edit"]),
      store:         new Set(["view", "create", "edit"]),
    },
  },
  {
    module: "rbac",
    labelKey: "rbac.matrix.modules.rbac",
    permissions: {
      administrator: new Set(["view", "create", "edit", "delete"]),
      accountant:    new Set(["view"]),
      agent:         new Set([]),
      courier:       new Set([]),
      store:         new Set([]),
    },
  },
];

// ─── Ruxsat belgisi ──────────────────────────────────────────────────────────

function PermCell({ allowed }: { allowed: boolean }) {
  return allowed ? (
    <Center>
      <ThemeIcon size={20} radius="xl" color="green" variant="light">
        <IconCheck size={12} />
      </ThemeIcon>
    </Center>
  ) : (
    <Center>
      <ThemeIcon size={20} radius="xl" color="gray" variant="light">
        <IconX size={12} />
      </ThemeIcon>
    </Center>
  );
}

// ─── Bosh komponent ──────────────────────────────────────────────────────────

export function RolePermissionsPage() {
  const { t } = useTranslation();

  return (
    <Can
      permission="rbac:view"
      fallback={
        <Box py="xl" ta="center">
          <Text c="dimmed">{t("rbac.access_denied")}</Text>
        </Box>
      }
    >
      <Box>
        <Group mb="xs" gap="sm">
          <ThemeIcon size={32} radius="md" color="red" variant="light">
            <IconShieldLock size={18} />
          </ThemeIcon>
          <Title order={3}>{t("rbac.page.title")}</Title>
        </Group>
        <Text c="dimmed" mb="xl" size="sm">
          {t("rbac.page.description")}
        </Text>

        {/* Rollar izohli badge'lar */}
        <Group gap="xs" mb="md">
          {ROLES.map((role) => (
            <Badge key={role} color={ROLE_COLORS[role]} variant="light">
              {t(`common.role.${role}`)}
            </Badge>
          ))}
        </Group>

        <ScrollArea>
          <Table
            withTableBorder
            withColumnBorders
            striped
            highlightOnHover
            style={{ minWidth: 900 }}
          >
            <Table.Thead>
              <Table.Tr>
                {/* Modul ustuni */}
                <Table.Th style={{ minWidth: 160 }}>
                  {t("rbac.matrix.module")}
                </Table.Th>
                {/* Amal ustuni */}
                <Table.Th style={{ minWidth: 100 }}>
                  {t("rbac.matrix.action")}
                </Table.Th>
                {/* Rol ustunlari */}
                {ROLES.map((role) => (
                  <Table.Th key={role} ta="center" style={{ minWidth: 110 }}>
                    <Badge color={ROLE_COLORS[role]} variant="light" size="sm">
                      {t(`common.role.${role}`)}
                    </Badge>
                  </Table.Th>
                ))}
              </Table.Tr>
            </Table.Thead>

            <Table.Tbody>
              {MATRIX.map((mod) =>
                ACTIONS.map((action, actionIdx) => (
                  <Table.Tr key={`${mod.module}-${action}`}>
                    {/* Birinchi amal qatorida modul nomi (rowSpan) */}
                    {actionIdx === 0 && (
                      <Table.Td
                        rowSpan={ACTIONS.length}
                        fw={600}
                        style={{
                          verticalAlign: "middle",
                          backgroundColor: "var(--mantine-color-default-hover)",
                        }}
                      >
                        {t(mod.labelKey)}
                        <Text size="xs" c="dimmed" ff="monospace">
                          {mod.module}
                        </Text>
                      </Table.Td>
                    )}

                    {/* Amal nomi */}
                    <Table.Td>
                      <Text size="sm" ff="monospace" c="dimmed">
                        {action}
                      </Text>
                    </Table.Td>

                    {/* Har rol uchun ruxsat belgisi */}
                    {ROLES.map((role) => (
                      <Table.Td key={role}>
                        <PermCell
                          allowed={mod.permissions[role].has(action)}
                        />
                      </Table.Td>
                    ))}
                  </Table.Tr>
                )),
              )}
            </Table.Tbody>
          </Table>
        </ScrollArea>

        <Text size="xs" c="dimmed" mt="md">
          {t("rbac.page.source_note")}
        </Text>
      </Box>
    </Can>
  );
}
