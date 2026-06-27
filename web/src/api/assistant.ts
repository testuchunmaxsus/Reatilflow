/**
 * Assistant API — AI Chat yordamchi.
 *
 * POST /assistant/chat → ChatOut
 *
 * PII-guard: history faqat matn; enterprise_id/store_id yuborilmaydi.
 * Fail-open: Groq yo'q → ai_enabled=false + statik javob.
 */

import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/api/client";

// ─── Tiplar ──────────────────────────────────────────────────────────────────

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatIn {
  message: string;
  history: ChatMessage[];
}

export interface ChatOut {
  reply: string;
  ai_enabled: boolean;
}

// ─── Chat mutation ────────────────────────────────────────────────────────────

export function useAssistantChat() {
  return useMutation({
    mutationFn: (data: ChatIn) =>
      apiClient.post<ChatOut>("/assistant/chat", data),
  });
}
