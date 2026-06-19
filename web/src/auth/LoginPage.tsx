/**
 * LoginPage — telefon + parol bilan kirish sahifasi.
 *
 * - Mantine form validatsiya
 * - i18n xato xabarlari
 * - ApiError message_key bo'yicha tarjima
 * - login muvaffaqiyatli bo'lsa avvalgi sahifaga yoki / ga qaytadi
 */

import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import {
  Box,
  Button,
  Center,
  Paper,
  PasswordInput,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useTranslation } from "react-i18next";
import { useAuth } from "./AuthContext";
import { ApiError } from "@/api/client";

interface LoginFormValues {
  phone: string;
  password: string;
}

export function LoginPage() {
  const { t } = useTranslation();
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [serverError, setServerError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Login muvaffaqiyatli bo'lganda qaytish sahifasi
  const from = (location.state as { from?: { pathname: string } } | null)?.from?.pathname ?? "/";

  const form = useForm<LoginFormValues>({
    initialValues: {
      phone: "",
      password: "",
    },
    validate: {
      phone: (value) => {
        if (!value.trim()) return t("validation.phone_required");
        if (!/^\+998\d{9}$/.test(value.trim())) return t("validation.phone_format");
        return null;
      },
      password: (value) => {
        if (!value) return t("validation.password_required");
        if (value.length < 6) return t("validation.password_min");
        return null;
      },
    },
  });

  const handleSubmit = async (values: LoginFormValues) => {
    setServerError(null);
    setIsLoading(true);
    try {
      await login({ phone: values.phone.trim(), password: values.password });
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        // message_key bo'yicha i18n tarjima; yo'q bo'lsa server matni
        const translatedKey = `api.${err.envelope.message_key}`;
        const translated = t(translatedKey, { defaultValue: "" });
        setServerError(translated || err.envelope.message || t("errors.unknown"));
      } else {
        setServerError(t("errors.network"));
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Center h="100vh" bg="gray.0">
      <Box w={{ base: "90%", sm: 400 }}>
        <Stack gap="md">
          {/* Logo / sarlavha */}
          <Stack gap={4} align="center">
            <Title order={2} c="blue.7">
              RETAIL
            </Title>
            <Text size="sm" c="dimmed">
              {t("login.subtitle")}
            </Text>
          </Stack>

          <Paper p="xl" shadow="sm" radius="md" withBorder>
            <form onSubmit={form.onSubmit(handleSubmit)}>
              <Stack gap="md">
                <TextInput
                  label={t("login.phone_label")}
                  placeholder="+998901234567"
                  autoComplete="tel"
                  inputMode="tel"
                  {...form.getInputProps("phone")}
                />

                <PasswordInput
                  label={t("login.password_label")}
                  placeholder={t("login.password_placeholder")}
                  autoComplete="current-password"
                  {...form.getInputProps("password")}
                />

                {serverError && (
                  <Text size="sm" c="red">
                    {serverError}
                  </Text>
                )}

                <Button type="submit" fullWidth loading={isLoading} mt="xs">
                  {t("login.submit")}
                </Button>
              </Stack>
            </form>
          </Paper>
        </Stack>
      </Box>
    </Center>
  );
}
