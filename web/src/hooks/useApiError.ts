/**
 * useApiError — ApiError envelope ni i18n bilan Mantine notifications ga chiqaradi.
 *
 * Foydalanish:
 *   const { showError } = useApiError();
 *   showError(error);
 */

import { useCallback } from "react";
import { notifications } from "@mantine/notifications";
import { useTranslation } from "react-i18next";
import { ApiError } from "@/api/client";

export function useApiError() {
  const { t } = useTranslation();

  const showError = useCallback(
    (error: unknown, fallbackKey = "errors.unknown") => {
      let message: string;

      if (error instanceof ApiError) {
        // Avval api.* kalitidan tarjima qidiramiz
        const i18nKey = `api.${error.envelope.message_key}`;
        const translated = t(i18nKey);
        // Agar tarjima topilmasa — backenddan kelgan xabarni ishlatamiz
        message =
          translated !== i18nKey
            ? translated
            : error.envelope.message ?? t(fallbackKey);
      } else if (error instanceof Error) {
        message =
          error.message.toLowerCase().includes("network") ||
          error.message.toLowerCase().includes("fetch")
            ? t("errors.network")
            : t(fallbackKey);
      } else {
        message = t(fallbackKey);
      }

      notifications.show({
        color: "red",
        title: t("errors.unknown"),
        message,
        autoClose: 5000,
      });
    },
    [t],
  );

  const showSuccess = useCallback(
    (messageKey: string) => {
      notifications.show({
        color: "green",
        message: t(messageKey),
        autoClose: 3000,
      });
    },
    [t],
  );

  return { showError, showSuccess };
}
