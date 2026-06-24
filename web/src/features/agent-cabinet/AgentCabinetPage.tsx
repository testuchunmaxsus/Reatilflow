/**
 * AgentCabinetPage — agent shaxsiy kabineti.
 *
 * Tarkib:
 * - Agent profili: ism, telefon, holat, rol
 * - Profil tahrirlash (faqat agent_cabinet:edit ruxsati bo'lsa)
 * - Biriktirilgan do'konlar ro'yxati (paginated)
 * - i18n: defaultValue orqali (agentCabinet.*)
 *
 * Backend endpointlari:
 *   GET   /auth/me           — profil
 *   PATCH /users/{id}        — profil yangilash
 *   GET   /customers/stores  — biriktirilgan do'konlar (agent scope)
 */

import {
  Badge,
  Box,
  Button,
  Card,
  Divider,
  Group,
  Loader,
  Modal,
  Pagination,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import {
  IconEdit,
  IconBuildingStore,
  IconUser,
  IconPhone,
  IconMapPin,
} from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import { useDisclosure } from "@mantine/hooks";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { Can } from "@/rbac/Can";
import { useAgentProfile, useUpdateAgentProfile, useAgentStores } from "./api/agentCabinetApi";
import { useApiError } from "@/hooks/useApiError";
import { usePagination } from "@/hooks/usePagination";
import type { AgentProfileUpdate } from "./types";

// ─── Profil kartasi ───────────────────────────────────────────────────────────

interface ProfileCardProps {
  onEdit: () => void;
}

function ProfileCard({ onEdit }: ProfileCardProps) {
  const { t } = useTranslation();
  const { data: profile, isLoading, isError } = useAgentProfile();

  if (isLoading) {
    return (
      <Group justify="center" py="xl">
        <Loader size="sm" />
        <Text c="dimmed" size="sm">{t("common.loading", { defaultValue: "Yuklanmoqda..." })}</Text>
      </Group>
    );
  }

  if (isError || !profile) {
    return (
      <Text c="red" size="sm">
        {t("errors.unknown", { defaultValue: "Noma'lum xato yuz berdi" })}
      </Text>
    );
  }

  return (
    <Card withBorder radius="sm" p="md">
      <Group justify="space-between" mb="sm">
        <Group gap="xs">
          <IconUser size={20} />
          <Title order={5}>
            {t("agentCabinet.profile.title", { defaultValue: "Mening profilim" })}
          </Title>
        </Group>
        <Can permission="agent_cabinet:edit">
          <Tooltip label={t("common.edit", { defaultValue: "Tahrirlash" })}>
            <Button
              size="xs"
              variant="light"
              leftSection={<IconEdit size={14} />}
              onClick={onEdit}
            >
              {t("common.edit", { defaultValue: "Tahrirlash" })}
            </Button>
          </Tooltip>
        </Can>
      </Group>
      <Divider mb="sm" />
      <Stack gap="xs">
        <Group gap="xs">
          <Text size="sm" c="dimmed" w={110}>
            {t("agentCabinet.profile.full_name", { defaultValue: "Ism:" })}
          </Text>
          <Text size="sm" fw={500}>{profile.full_name}</Text>
        </Group>
        <Group gap="xs">
          <Text size="sm" c="dimmed" w={110}>
            <Group gap={4} component="span">
              <IconPhone size={14} />
              {t("agentCabinet.profile.phone", { defaultValue: "Telefon:" })}
            </Group>
          </Text>
          <Text size="sm" ff="monospace">{profile.phone}</Text>
        </Group>
        <Group gap="xs">
          <Text size="sm" c="dimmed" w={110}>
            {t("agentCabinet.profile.role", { defaultValue: "Rol:" })}
          </Text>
          <Badge variant="light" color="blue" size="sm">
            {t(`common.role.${profile.role}`, { defaultValue: profile.role })}
          </Badge>
        </Group>
        <Group gap="xs">
          <Text size="sm" c="dimmed" w={110}>
            {t("agentCabinet.profile.status", { defaultValue: "Holat:" })}
          </Text>
          <Badge
            variant="dot"
            color={profile.is_active ? "green" : "gray"}
            size="sm"
          >
            {profile.is_active
              ? t("users.status.active", { defaultValue: "Faol" })
              : t("users.status.inactive", { defaultValue: "Nofaol" })}
          </Badge>
        </Group>
        <Group gap="xs">
          <Text size="sm" c="dimmed" w={110}>
            {t("agentCabinet.profile.locale", { defaultValue: "Til:" })}
          </Text>
          <Text size="sm">{profile.locale === "uz" ? "O'zbek" : "Русский"}</Text>
        </Group>
      </Stack>
    </Card>
  );
}

// ─── Profil tahrirlash modali ─────────────────────────────────────────────────

interface EditProfileModalProps {
  opened: boolean;
  onClose: () => void;
}

function EditProfileModal({ opened, onClose }: EditProfileModalProps) {
  const { t } = useTranslation();
  const { showError } = useApiError();
  const { data: profile } = useAgentProfile();
  const updateProfile = useUpdateAgentProfile();

  const form = useForm<{ full_name: string; locale: "uz" | "ru" }>({
    initialValues: {
      full_name: profile?.full_name ?? "",
      locale: profile?.locale ?? "uz",
    },
    validate: {
      full_name: (v) =>
        v.trim().length < 2
          ? t("agentCabinet.edit.full_name_min", { defaultValue: "Ism kamida 2 belgi" })
          : null,
    },
  });

  // Profil o'zgarganda forma qiymatlarini yangilaymiz
  const handleOpen = () => {
    if (profile) {
      form.setValues({ full_name: profile.full_name, locale: profile.locale });
    }
  };

  const handleSubmit = async (values: typeof form.values) => {
    // PATCH /auth/me — self-service (id/version kerak emas)
    const data: AgentProfileUpdate = {
      full_name: values.full_name.trim(),
      locale: values.locale,
    };
    try {
      await updateProfile.mutateAsync(data);
      notifications.show({
        color: "green",
        message: t("agentCabinet.edit.saved", { defaultValue: "Profil saqlandi" }),
      });
      onClose();
    } catch (err) {
      showError(err);
    }
  };

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={t("agentCabinet.edit.title", { defaultValue: "Profilni tahrirlash" })}
      centered
      onLoadedData={handleOpen}
    >
      <form onSubmit={form.onSubmit((v) => { void handleSubmit(v); })}>
        <Stack gap="sm">
          <TextInput
            label={t("agentCabinet.profile.full_name", { defaultValue: "Ism" })}
            required
            {...form.getInputProps("full_name")}
          />
          <Select
            label={t("agentCabinet.profile.locale", { defaultValue: "Til" })}
            data={[
              { value: "uz", label: "O'zbek" },
              { value: "ru", label: "Русский" },
            ]}
            allowDeselect={false}
            {...form.getInputProps("locale")}
          />
          <Group justify="flex-end" mt="xs">
            <Button variant="subtle" onClick={onClose}>
              {t("common.cancel", { defaultValue: "Bekor qilish" })}
            </Button>
            <Button type="submit" loading={updateProfile.isPending}>
              {t("common.save", { defaultValue: "Saqlash" })}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}

// ─── Do'konlar ro'yxati ───────────────────────────────────────────────────────

function StoresSection() {
  const { t } = useTranslation();
  const { page, setPage, offset, pageSize, getTotalPages } = usePagination(20);

  const { data, isLoading, isError } = useAgentStores({
    limit: pageSize,
    offset,
  });

  const totalPages = getTotalPages(data?.total);

  return (
    <Stack gap="sm">
      <Group gap="xs">
        <IconBuildingStore size={20} />
        <Title order={5}>
          {t("agentCabinet.stores.title", { defaultValue: "Biriktirilgan do'konlar" })}
        </Title>
        {data && (
          <Badge variant="light" color="gray" size="sm">
            {data.total}
          </Badge>
        )}
      </Group>

      {isLoading ? (
        <Group justify="center" py="xl">
          <Loader size="sm" />
          <Text c="dimmed" size="sm">
            {t("common.loading", { defaultValue: "Yuklanmoqda..." })}
          </Text>
        </Group>
      ) : isError ? (
        <Box py="xl" ta="center">
          <Text c="red" size="sm">
            {t("errors.unknown", { defaultValue: "Noma'lum xato yuz berdi" })}
          </Text>
        </Box>
      ) : !data?.items.length ? (
        <Box py="xl" ta="center">
          <Text c="dimmed" size="sm">
            {t("agentCabinet.stores.empty", { defaultValue: "Biriktirilgan do'konlar topilmadi" })}
          </Text>
        </Box>
      ) : (
        <>
          <Table.ScrollContainer minWidth={600}>
            <Table striped highlightOnHover withTableBorder>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>
                    {t("agentCabinet.stores.col_name", { defaultValue: "Do'kon nomi" })}
                  </Table.Th>
                  <Table.Th>
                    {t("agentCabinet.stores.col_phone", { defaultValue: "Telefon" })}
                  </Table.Th>
                  <Table.Th>
                    <Group gap={4} component="span">
                      <IconMapPin size={14} />
                      {t("agentCabinet.stores.col_address", { defaultValue: "Manzil" })}
                    </Group>
                  </Table.Th>
                  <Table.Th>
                    {t("agentCabinet.stores.col_owner", { defaultValue: "Egasi" })}
                  </Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {data.items.map((store) => (
                  <Table.Tr key={store.id}>
                    <Table.Td>
                      <Text size="sm" fw={500} lineClamp={1}>
                        {store.name}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" ff="monospace">
                        {store.phone ?? "—"}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" c="dimmed" lineClamp={1}>
                        {store.address ?? "—"}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" lineClamp={1}>
                        {store.owner_name ?? "—"}
                      </Text>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          {totalPages > 1 && (
            <Group justify="center">
              <Pagination
                value={page}
                onChange={setPage}
                total={totalPages}
                size="sm"
              />
            </Group>
          )}
        </>
      )}
    </Stack>
  );
}

// ─── Asosiy sahifa ────────────────────────────────────────────────────────────

export function AgentCabinetPage() {
  const { t } = useTranslation();
  const [editOpened, { open: openEdit, close: closeEdit }] = useDisclosure(false);

  return (
    <Stack gap="lg">
      <Title order={3}>
        {t("agentCabinet.page_title", { defaultValue: "Agent kabineti" })}
      </Title>

      {/* Profil katrasi */}
      <ProfileCard onEdit={openEdit} />

      <Divider />

      {/* Biriktirilgan do'konlar */}
      <StoresSection />

      {/* Profil tahrirlash modal */}
      <EditProfileModal opened={editOpened} onClose={closeEdit} />
    </Stack>
  );
}
