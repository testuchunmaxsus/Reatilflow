/**
 * API klient qatlami
 *
 * Xususiyatlar:
 * - `Authorization: Bearer <access_token>` har so'rovga qo'shiladi
 * - `Accept-Language` joriy locale bilan yuboriladi
 * - 401 → silent refresh: /auth/refresh bilan yangi token olinadi,
 *   asl so'rov qayta yuboriladi (1 marta)
 * - refresh ham 401 bo'lsa → logout (token tozalanadi)
 * - Xato envelope `{message_key, message, detail}` parse qilinadi
 *
 * Xavfsizlik eslatmasi (reviewerlar uchun):
 * - access_token — faqat xotirada (state), localStorage/sessionStorage'ga
 *   YOZILMAYDI (XSS da o'g'irlanmaydi)
 * - refresh_token — localStorage'da saqlanadi (XSS tradeoff; production da
 *   httpOnly cookie yaxshiroq, lekin Tauri desktop SPA uchun hozircha shunday)
 */

import { type ErrorEnvelope, type TokenPair } from "./types";

// ─── Konstantalar ─────────────────────────────────────────────────────────

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
  "http://localhost:8000";

const REFRESH_TOKEN_KEY = "retail_refresh_token";

// ─── Token boshqaruvi ────────────────────────────────────────────────────

/** In-memory access token (XSS dan xavfsiz) */
let _accessToken: string | null = null;

/** Refresh token localStorage da (XSS tradeoff — izohi yuqorida) */
export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setTokens(pair: TokenPair): void {
  _accessToken = pair.access_token;
  localStorage.setItem(REFRESH_TOKEN_KEY, pair.refresh_token);
}

export function clearTokens(): void {
  _accessToken = null;
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

export function getAccessToken(): string | null {
  return _accessToken;
}

// ─── Locale ───────────────────────────────────────────────────────────────

/**
 * Joriy locale — i18next dan olinadi (yoki localStorage fallback).
 * Circular import'dan qochish uchun to'g'ridan-to'g'ri localStorage'dan o'qiydi.
 */
function getCurrentLocale(): string {
  return localStorage.getItem("i18nextLng") ?? "uz";
}

// ─── Refresh mutex ────────────────────────────────────────────────────────

/**
 * Bir vaqtda bir nechta 401 kelganda parallel refresh so'rovlarini oldini olish.
 * Birinchi refresh boshlanadi, qolganlar natijani kutadi.
 */
let _refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (_refreshPromise) {
    return _refreshPromise;
  }

  _refreshPromise = (async () => {
    const refreshToken = getRefreshToken();
    if (!refreshToken) {
      return null;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (!response.ok) {
        // Refresh ham muvaffaqiyatsiz — logout kerak
        clearTokens();
        // Sahifani login ga yo'naltirish (Auth context orqali)
        window.dispatchEvent(new CustomEvent("retail:auth:logout"));
        return null;
      }

      const data = (await response.json()) as TokenPair;
      setTokens(data);
      return data.access_token;
    } catch {
      clearTokens();
      window.dispatchEvent(new CustomEvent("retail:auth:logout"));
      return null;
    } finally {
      _refreshPromise = null;
    }
  })();

  return _refreshPromise;
}

// ─── Typed API xato ───────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly envelope: ErrorEnvelope,
  ) {
    super(envelope.message ?? `HTTP ${status}`);
    this.name = "ApiError";
  }
}

// ─── So'rov yuboruvchi ────────────────────────────────────────────────────

export interface RequestOptions extends RequestInit {
  /** URLdan keyingi path, masalan "/catalog/products?page=1" */
  path: string;
  /** Agar true bo'lsa, 401 da refresh qilinmaydi (login/refresh endpointlari uchun) */
  skipAuth?: boolean;
  /**
   * Agar true bo'lsa, Content-Type avtomatik qo'shilmaydi.
   * FormData (multipart/form-data) yuborishda brauzer o'zi boundary bilan
   * Content-Type ni belgilaydi — qo'lda qo'yish boundary ni buzadi.
   */
  skipContentType?: boolean;
}

/**
 * Asosiy HTTP so'rov yuboruvchi.
 *
 * @throws {ApiError} — backend xato envelope bilan javob berganda
 * @throws {Error} — tarmoq xatosi yoki JSON parse xatosi
 */
async function request<T>(options: RequestOptions): Promise<T> {
  const {
    path,
    skipAuth = false,
    skipContentType = false,
    headers: extraHeaders,
    ...rest
  } = options;

  const headers: Record<string, string> = {
    ...(skipContentType ? {} : { "Content-Type": "application/json" }),
    "Accept-Language": getCurrentLocale(),
    ...(extraHeaders as Record<string, string>),
  };

  if (!skipAuth && _accessToken) {
    headers["Authorization"] = `Bearer ${_accessToken}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    headers,
  });

  // 401 — access token muddati tugagan → silent refresh
  if (response.status === 401 && !skipAuth) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      // Asl so'rovni yangi token bilan qayta yubor
      headers["Authorization"] = `Bearer ${newToken}`;
      const retryResponse = await fetch(`${API_BASE_URL}${path}`, {
        ...rest,
        headers,
      });
      return handleResponse<T>(retryResponse);
    }
    // refresh muvaffaqiyatsiz — AuthContext logout event orqali hal qiladi
    const errorEnvelope: ErrorEnvelope = {
      message_key: "auth.authentication_required",
      message: "Autentifikatsiya talab qilinadi",
      detail: null,
    };
    throw new ApiError(401, errorEnvelope);
  }

  return handleResponse<T>(response);
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  const isJson = contentType.includes("application/json");

  if (!response.ok) {
    if (isJson) {
      const envelope = (await response.json()) as ErrorEnvelope;
      throw new ApiError(response.status, envelope);
    }
    const errorEnvelope: ErrorEnvelope = {
      message_key: "common.internal_error",
      message: `HTTP ${response.status}`,
      detail: null,
    };
    throw new ApiError(response.status, errorEnvelope);
  }

  if (!isJson) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

// ─── Ommaviy API ───────────────────────────────────────────────────────────

/** Typed HTTP metodlari */
export const apiClient = {
  get<T>(path: string, options?: Omit<RequestOptions, "path" | "method">): Promise<T> {
    return request<T>({ ...options, path, method: "GET" });
  },

  post<T>(
    path: string,
    body?: unknown,
    options?: Omit<RequestOptions, "path" | "method" | "body">,
  ): Promise<T> {
    return request<T>({
      ...options,
      path,
      method: "POST",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  },

  put<T>(
    path: string,
    body?: unknown,
    options?: Omit<RequestOptions, "path" | "method" | "body">,
  ): Promise<T> {
    return request<T>({
      ...options,
      path,
      method: "PUT",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  },

  patch<T>(
    path: string,
    body?: unknown,
    options?: Omit<RequestOptions, "path" | "method" | "body">,
  ): Promise<T> {
    return request<T>({
      ...options,
      path,
      method: "PATCH",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  },

  delete<T>(
    path: string,
    options?: Omit<RequestOptions, "path" | "method">,
  ): Promise<T> {
    return request<T>({ ...options, path, method: "DELETE" });
  },

  /**
   * Multipart/form-data fayl yuklash.
   *
   * Content-Type qo'shilmaydi — brauzer boundary bilan o'zi belgilaydi.
   * Authorization, Accept-Language va 401→refresh oqimi boshqa metodlar
   * kabi mavjud `request()` orqali ishlaydi.
   */
  upload<T>(
    path: string,
    formData: FormData,
    options?: Omit<RequestOptions, "path" | "method" | "body" | "skipContentType">,
  ): Promise<T> {
    return request<T>({
      ...options,
      path,
      method: "POST",
      body: formData,
      skipContentType: true,
    });
  },
};
