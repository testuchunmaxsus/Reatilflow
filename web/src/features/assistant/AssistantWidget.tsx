/**
 * AssistantWidget — suzuvchi AI Chat yordamchi (har sahifada ko'rinadigan).
 *
 * Xususiyatlar:
 * - Pastki o'ng burchakda suzuvchi tugma
 * - Chat oynasi ochiladi/yopiladi
 * - history client'da saqlanadi (max 6 ta xabar)
 * - POST /assistant/chat — Groq llama-3.3 o'zbekcha javob
 * - ai_enabled=false → "qo'llanma" badge
 * - RBAC: "assistant:view" ruxsati tekshiriladi
 * - PII-guard: enterprise_id/store_id yuborilmaydi
 */

import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Card,
  Group,
  Loader,
  Paper,
  ScrollArea,
  Stack,
  Text,
  Textarea,
  Tooltip,
} from "@mantine/core";
import {
  IconMessage,
  IconSend,
  IconX,
} from "@tabler/icons-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { usePermissions } from "@/rbac/usePermissions";
import { useAssistantChat, type ChatMessage } from "@/api/assistant";

// ─── Xabar ko'rsatkichi ───────────────────────────────────────────────────────

interface MessageBubbleProps {
  message: ChatMessage;
}

function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";
  return (
    <Box
      style={{
        display: "flex",
        justifyContent: isUser ? "flex-end" : "flex-start",
      }}
    >
      <Paper
        p="xs"
        radius="md"
        style={{
          maxWidth: "85%",
          background: isUser ? "var(--mantine-color-blue-6)" : "var(--mantine-color-gray-1)",
          color: isUser ? "white" : "inherit",
        }}
      >
        <Text size="sm" style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
          {message.content}
        </Text>
      </Paper>
    </Box>
  );
}

// ─── Widget ichki holat ────────────────────────────────────────────────────────

const MAX_HISTORY = 6;

function ChatPanel({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const chat = useAssistantChat();

  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [aiEnabled, setAiEnabled] = useState<boolean | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Yangi xabar kelganda pastga scroll
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [history]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || chat.isPending) return;

    // Foydalanuvchi xabarini qo'shish
    const userMsg: ChatMessage = { role: "user", content: text };
    const updatedHistory = [...history, userMsg];
    setHistory(updatedHistory);
    setInput("");

    try {
      // history dan max so'nggi MAX_HISTORY ta (oxirgi user xabar kiritilgan)
      const truncated = updatedHistory.slice(-MAX_HISTORY);
      const result = await chat.mutateAsync({
        message: text,
        history: truncated.slice(0, -1), // oxirgi (yangi) xabarni ajratib message da yuboramiz
      });
      setAiEnabled(result.ai_enabled);
      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: result.reply,
      };
      setHistory((prev) => [...prev, assistantMsg]);
    } catch {
      // Xato bo'lsa ham UI'ni bloklamaymiz
      const errorMsg: ChatMessage = {
        role: "assistant",
        content: t("assistant.error_fallback", {
          defaultValue:
            "Kechirasiz, hozirda javob bera olmayapman. Qayta urinib ko'ring.",
        }),
      };
      setHistory((prev) => [...prev, errorMsg]);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  return (
    <Card
      withBorder
      shadow="lg"
      radius="md"
      style={{
        position: "fixed",
        bottom: 80,
        right: 16,
        width: 340,
        maxWidth: "calc(100vw - 32px)",
        zIndex: 1000,
        display: "flex",
        flexDirection: "column",
        maxHeight: "70vh",
      }}
      p={0}
    >
      {/* Header */}
      <Box
        px="md"
        py="sm"
        style={{
          background: "var(--mantine-color-blue-6)",
          borderRadius: "var(--mantine-radius-md) var(--mantine-radius-md) 0 0",
        }}
      >
        <Group justify="space-between">
          <Group gap="xs">
            <Text c="white" fw={600} size="sm">
              {t("assistant.title", { defaultValue: "AI Yordamchi" })}
            </Text>
            {aiEnabled === false && (
              <Badge color="gray" variant="filled" size="xs">
                {t("assistant.offline_badge", { defaultValue: "qo'llanma" })}
              </Badge>
            )}
          </Group>
          <ActionIcon
            variant="subtle"
            color="white"
            size="sm"
            onClick={onClose}
            aria-label={t("common.close")}
          >
            <IconX size={16} />
          </ActionIcon>
        </Group>
      </Box>

      {/* Xabarlar */}
      <ScrollArea
        viewportRef={scrollRef}
        flex={1}
        style={{ minHeight: 200, maxHeight: "50vh" }}
        px="xs"
        py="xs"
      >
        {history.length === 0 ? (
          <Stack gap="xs" py="md" align="center">
            <Text size="sm" c="dimmed" ta="center">
              {t("assistant.greeting", {
                defaultValue:
                  "Salom! Men RETAIL tizimi bo'yicha yordam beraman. Savol bering.",
              })}
            </Text>
          </Stack>
        ) : (
          <Stack gap="xs">
            {history.map((msg, i) => (
              <MessageBubble key={i} message={msg} />
            ))}
            {chat.isPending && (
              <Group gap="xs" pl="xs">
                <Loader size="xs" />
                <Text size="xs" c="dimmed">
                  {t("assistant.thinking", { defaultValue: "Javob tayyorlanmoqda..." })}
                </Text>
              </Group>
            )}
          </Stack>
        )}
      </ScrollArea>

      {/* Input */}
      <Box px="xs" pb="xs" pt={4}>
        <Group gap="xs" align="flex-end">
          <Textarea
            flex={1}
            size="xs"
            placeholder={t("assistant.input_placeholder", {
              defaultValue: "Savol yozing... (Enter — yuborish)",
            })}
            value={input}
            onChange={(e) => setInput(e.currentTarget.value)}
            onKeyDown={handleKeyDown}
            maxLength={1000}
            autosize
            minRows={1}
            maxRows={4}
            disabled={chat.isPending}
          />
          <Button
            size="xs"
            px="xs"
            onClick={() => {
              void handleSend();
            }}
            disabled={!input.trim() || chat.isPending}
            aria-label={t("assistant.send", { defaultValue: "Yuborish" })}
          >
            <IconSend size={14} />
          </Button>
        </Group>
      </Box>
    </Card>
  );
}

// ─── Tashqi widget (suzuvchi tugma + panel) ───────────────────────────────────

export function AssistantWidget() {
  const { t } = useTranslation();
  const { can } = usePermissions();
  const [open, setOpen] = useState(false);

  // assistant:view ruxsati yo'q bo'lsa widget ko'rinmaydi
  if (!can("assistant:view")) {
    return null;
  }

  return (
    <>
      {open && <ChatPanel onClose={() => setOpen(false)} />}

      <Tooltip
        label={t("assistant.toggle_tooltip", { defaultValue: "AI Yordamchi" })}
        position="left"
      >
        <ActionIcon
          size="xl"
          radius="xl"
          color="blue"
          variant="filled"
          style={{
            position: "fixed",
            bottom: 20,
            right: 16,
            zIndex: 1001,
            boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
          }}
          onClick={() => setOpen((v) => !v)}
          aria-label={t("assistant.toggle_tooltip", { defaultValue: "AI Yordamchi" })}
        >
          {open ? <IconX size={20} /> : <IconMessage size={20} />}
        </ActionIcon>
      </Tooltip>
    </>
  );
}
