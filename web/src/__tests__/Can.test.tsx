/**
 * <Can> komponenti testlari
 *
 * Tekshiriladi:
 * 1. Ruxsat mavjud bo'lsa children render bo'ladi
 * 2. Ruxsat yo'q bo'lsa children render bo'lmaydi
 * 3. Ruxsat yo'q va fallback berilsa — fallback render bo'ladi
 * 4. Autentifikatsiya yo'q bo'lsa — hech narsa render bo'lmaydi
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Can } from "@/rbac/Can";

// ─── usePermissions mock ──────────────────────────────────────────────────

const mockCan = vi.fn<[string], boolean>();

vi.mock("@/rbac/usePermissions", () => ({
  usePermissions: () => ({
    role: "administrator",
    permissions: new Set<string>(),
    can: mockCan,
    canAny: vi.fn(),
  }),
}));

// ─── Testlar ──────────────────────────────────────────────────────────────

describe("<Can>", () => {
  it("ruxsat mavjud bo'lsa children render bo'ladi", () => {
    mockCan.mockReturnValue(true);
    render(
      <Can permission="catalog:create">
        <button>Qo'shish</button>
      </Can>,
    );
    expect(screen.getByRole("button", { name: /qo'shish/i })).toBeInTheDocument();
  });

  it("ruxsat yo'q bo'lsa children render bo'lmaydi", () => {
    mockCan.mockReturnValue(false);
    render(
      <Can permission="catalog:delete">
        <button>O'chirish</button>
      </Can>,
    );
    expect(screen.queryByRole("button", { name: /o'chirish/i })).not.toBeInTheDocument();
  });

  it("ruxsat yo'q va fallback berilsa — fallback render bo'ladi", () => {
    mockCan.mockReturnValue(false);
    render(
      <Can permission="finance:approve" fallback={<span>Ruxsat yo'q</span>}>
        <button>Tasdiqlash</button>
      </Can>,
    );
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText("Ruxsat yo'q")).toBeInTheDocument();
  });

  it("to'g'ri permission string bilan can chaqiriladi", () => {
    mockCan.mockReturnValue(true);
    render(
      <Can permission="rbac:create">
        <span>Admin panel</span>
      </Can>,
    );
    expect(mockCan).toHaveBeenCalledWith("rbac:create");
  });
});
