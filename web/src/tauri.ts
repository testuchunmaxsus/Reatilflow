/**
 * Tauri feature-detection yordamchilari.
 *
 * Veb va desktop (Tauri) bir xil React kod bazasida ishlaydi.
 * Tauri-ga xos funksiyalarni ishlatishdan oldin `isTauri()` tekshiriladi.
 *
 * Tauri nativ API: `@tauri-apps/api` paketi (T8+ da qo'shiladi).
 */

/**
 * Ilova Tauri desktop qobig'ida ishlayapti deb aniqlaydi.
 * `window.__TAURI__` Tauri ilovalarida global o'zgaruvchi sifatida mavjud.
 */
export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI__" in window;
}

/**
 * Platformani qaytaradi: "tauri" | "web"
 */
export function getPlatform(): "tauri" | "web" {
  return isTauri() ? "tauri" : "web";
}

/**
 * Tauri da nativ dialog, vebda oddiy browser dialog.
 * Kengaytirish uchun: T8+ da `@tauri-apps/api/dialog` bilan almashtirish.
 */
export async function openConfirmDialog(message: string): Promise<boolean> {
  if (isTauri()) {
    // Kelajakda: const { confirm } = await import("@tauri-apps/api/dialog");
    // return confirm(message);
    return window.confirm(message);
  }
  return window.confirm(message);
}
