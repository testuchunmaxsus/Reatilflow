/**
 * apiClient.upload testlari
 *
 * Tekshiriladi:
 * 1. FormData yuborilganda Content-Type qo'lda qo'yilmaydi
 *    (brauzer boundary bilan o'zi belgilaydi)
 * 2. Authorization: Bearer header qo'shiladi
 * 3. Accept-Language header qo'shiladi
 * 4. 401 → refreshAccessToken chaqiriladi → asl so'rov yangi token bilan retry qilinadi
 * 5. refresh ham 401 bo'lsa → ApiError(401) throw qilinadi
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// ─── fetch mock ───────────────────────────────────────────────────────────────

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

// ─── Import after stubbing ────────────────────────────────────────────────────

// Dynamic import ishlatiladi — chunki client.ts modul darajasida
// _accessToken holatini saqlaydi; har test uchun fresh modul kerak emas
// lekin token state ni reset qilish uchun setTokens/clearTokens ishlatamiz.
import {
  apiClient,
  setTokens,
  clearTokens,
  ApiError,
} from "@/api/client";

// ─── Yordamchi: Response yasash ───────────────────────────────────────────────

function makeJsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

// ─── Testlar ──────────────────────────────────────────────────────────────────

describe("apiClient.upload", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Har test boshida tokenlarni tozala
    clearTokens();
  });

  afterEach(() => {
    clearTokens();
  });

  it("FormData yuborilganda Content-Type header qo'yilmaydi", async () => {
    // Arrange
    setTokens({ access_token: "tok-abc", refresh_token: "ref-abc", token_type: "bearer" });
    const formData = new FormData();
    formData.append("file", new Blob(["img"], { type: "image/png" }), "photo.png");

    mockFetch.mockResolvedValueOnce(
      makeJsonResponse({ id: "prod-1", photo_url: "/photos/1.png" }),
    );

    // Act
    await apiClient.upload("/catalog/products/prod-1/photo", formData);

    // Assert — fetch bir marta chaqirildi
    expect(mockFetch).toHaveBeenCalledOnce();

    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Record<string, string>;

    // Content-Type brauzerga qoldirilishi shart — qo'lda qo'yilmagan
    expect(headers["Content-Type"]).toBeUndefined();
    expect(headers["content-type"]).toBeUndefined();

    // body FormData bo'lishi shart
    expect(init.body).toBe(formData);
  });

  it("Authorization: Bearer va Accept-Language headerlari qo'shiladi", async () => {
    // Arrange
    setTokens({ access_token: "tok-xyz", refresh_token: "ref-xyz", token_type: "bearer" });
    const formData = new FormData();

    mockFetch.mockResolvedValueOnce(
      makeJsonResponse({ id: "prod-2", photo_url: "/photos/2.png" }),
    );

    // Act
    await apiClient.upload("/catalog/products/prod-2/photo", formData);

    // Assert
    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Record<string, string>;

    expect(headers["Authorization"]).toBe("Bearer tok-xyz");
    expect(headers["Accept-Language"]).toBeDefined();
  });

  it("401 → refreshAccessToken chaqiriladi → yangi token bilan retry", async () => {
    // Arrange — dastlabki access token
    setTokens({ access_token: "tok-old", refresh_token: "ref-valid", token_type: "bearer" });
    const formData = new FormData();
    formData.append("file", new Blob(["data"], { type: "image/png" }), "f.png");

    const successBody = { id: "prod-3", photo_url: "/photos/3.png" };

    mockFetch
      // 1-chi call: upload → 401
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      // 2-chi call: /auth/refresh → yangi tokenlar
      .mockResolvedValueOnce(
        makeJsonResponse({
          access_token: "tok-new",
          refresh_token: "ref-new",
          token_type: "bearer",
        }),
      )
      // 3-chi call: upload retry → 200
      .mockResolvedValueOnce(makeJsonResponse(successBody));

    // Act
    const result = await apiClient.upload("/catalog/products/prod-3/photo", formData);

    // Assert
    expect(result).toEqual(successBody);
    // Jami 3 ta fetch: upload, refresh, upload-retry
    expect(mockFetch).toHaveBeenCalledTimes(3);

    // Refresh so'rovi to'g'ri endpoint ga ketgan
    const [refreshUrl] = mockFetch.mock.calls[1] as [string, RequestInit];
    expect(refreshUrl).toContain("/auth/refresh");

    // Retry da yangi token ishlatilgan
    const [, retryInit] = mockFetch.mock.calls[2] as [string, RequestInit];
    const retryHeaders = retryInit.headers as Record<string, string>;
    expect(retryHeaders["Authorization"]).toBe("Bearer tok-new");

    // Retry da ham Content-Type qo'yilmagan
    expect(retryHeaders["Content-Type"]).toBeUndefined();
    expect(retryHeaders["content-type"]).toBeUndefined();
  });

  it("refresh ham 401 bo'lsa → ApiError(401) throw qilinadi", async () => {
    // Arrange
    setTokens({ access_token: "tok-stale", refresh_token: "ref-expired", token_type: "bearer" });
    const formData = new FormData();

    mockFetch
      // 1-chi call: upload → 401
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      // 2-chi call: /auth/refresh → 401
      .mockResolvedValueOnce(new Response(null, { status: 401 }));

    // Act & Assert
    await expect(
      apiClient.upload("/catalog/products/prod-4/photo", formData),
    ).rejects.toBeInstanceOf(ApiError);

    // Jami 2 ta fetch: upload, refresh (retry yo'q)
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });
});
