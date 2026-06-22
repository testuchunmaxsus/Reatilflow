/**
 * Sana yordamchi funksiyalari — timezone-xavfsiz DATE (vaqtsiz) ishlovi.
 *
 * MUAMMO: `new Date("2026-06-20")` UTC yarim tun deb talqin qilinadi va
 * `date.toISOString().slice(0,10)` UTC sanani qaytaradi. O'zbekiston UTC+5 —
 * mahalliy yarim tunda tanlangan sana UTC'da bir kun oldin bo'lib qoladi
 * (masalan, 20-iyun → "2026-06-19"). DATE maydonlari (promo/shartnoma muddati)
 * uchun bu noto'g'ri. Quyidagi funksiyalar MAHALLIY sana komponentlari bilan
 * ishlaydi — timezone siljishisiz.
 */

/**
 * ISO sana satrini qisqacha ko'rsatish uchun formatlaydi.
 * Masalan: "2026-06-01T10:00:00Z" → "01.06.2026"
 */
export function formatDate(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

/** Date obyektini mahalliy "YYYY-MM-DD" satriga aylantiradi (UTC emas). */
export function toLocalYMD(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/**
 * "YYYY-MM-DD" satrini MAHALLIY Date sifatida parse qiladi (UTC emas).
 * Yaroqsiz/bo'sh satr uchun null qaytaradi.
 */
export function parseYMD(s: string | null | undefined): Date | null {
  if (!s) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) {
    const fallback = new Date(s);
    return Number.isNaN(fallback.getTime()) ? null : fallback;
  }
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}
