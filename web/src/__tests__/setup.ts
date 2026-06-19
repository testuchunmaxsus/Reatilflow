/**
 * Vitest test sozlamalari
 */

import "@testing-library/jest-dom";

// i18next mock — test paytida tarjimalar ishlashi uchun
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import uz from "@/i18n/locales/uz.json";
import ru from "@/i18n/locales/ru.json";

i18n.use(initReactI18next).init({
  lng: "uz",
  fallbackLng: "uz",
  resources: {
    uz: { translation: uz },
    ru: { translation: ru },
  },
  interpolation: { escapeValue: false },
});

// window.matchMedia mock (Mantine uchun kerak)
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

// localStorage mock
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value; },
    removeItem: (key: string) => { delete store[key]; },
    clear: () => { store = {}; },
  };
})();
Object.defineProperty(window, "localStorage", { value: localStorageMock });

// ResizeObserver mock (Mantine ScrollArea / Select uchun jsdom da yo'q)
globalThis.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// IntersectionObserver mock (Mantine uchun kerak bo'lishi mumkin)
globalThis.IntersectionObserver = class IntersectionObserver {
  root = null;
  rootMargin = "";
  thresholds: readonly number[] = [];
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords(): IntersectionObserverEntry[] { return []; }
} as unknown as typeof IntersectionObserver;
