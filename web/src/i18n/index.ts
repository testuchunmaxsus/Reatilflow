/**
 * i18next sozlamalari — uz/ru ikki tilli.
 *
 * - Standart til: uz
 * - Saqlash: localStorage (i18nextLng kalit)
 * - Til almashtirish: LanguageSwitcher komponenti orqali
 * - API ga Accept-Language: apiClient client.ts da getCurrentLocale() orqali
 */

import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import uz from "./locales/uz.json";
import ru from "./locales/ru.json";

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      uz: { translation: uz },
      ru: { translation: ru },
    },
    fallbackLng: "uz",
    supportedLngs: ["uz", "ru"],
    interpolation: {
      escapeValue: false, // React XSS himoyasi o'zi bajaradi
    },
    detection: {
      // Til aniqlash tartibi: localStorage → navigator
      order: ["localStorage", "navigator"],
      lookupLocalStorage: "i18nextLng",
      caches: ["localStorage"],
    },
    // `uz` yoki `ru` bo'lmasa uz ga fallback
    nonExplicitSupportedLngs: false,
  });

export default i18n;
