import { useCallback, useEffect, useRef, useState } from "react";
import { Brain, Sparkles } from "lucide-react";
import { fetchProfile, sendFeedback, streamChat, uploadFile } from "./api";
import { ChatInput } from "./components/ChatInput";
import { ChatMessage } from "./components/ChatMessage";
import { MemoryPanel } from "./components/MemoryPanel";
import { Sidebar } from "./components/Sidebar";
import { ThemeToggle } from "./components/ThemeToggle";
import { useTheme } from "./hooks/useTheme";
import { useThreads } from "./hooks/useThreads";
import type { Claim, Message, Source } from "./types";

const SUGGESTIONS = [
  "Запомни: меня зовут Алекс, я backend-разработчик",
  "Где я работаю и чем занимаюсь?",
  "Что ты знаешь обо мне из прошлых сообщений?",
];

function titleFromMessage(text: string) {
  const t = text.trim().slice(0, 48);
  return t.length < text.trim().length ? `${t}…` : t || "Новый чат";
}

export default function App() {
  const {
    threads,
    activeThread,
    activeId,
    setActiveId,
    updateActive,
    createThread,
    deleteThread,
  } = useThreads();

  const { theme, toggle: toggleTheme } = useTheme();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [claims, setClaims] = useState<Claim[]>([]);
  const [claimsLoading, setClaimsLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [useLlm, setUseLlm] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const refreshClaims = useCallback(async () => {
    setClaimsLoading(true);
    try {
      setClaims(await fetchProfile());
    } catch {
      /* offline */
    } finally {
      setClaimsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshClaims();
  }, [refreshClaims, activeId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeThread.messages, busy]);

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const appendMessage = (msg: Message) => {
    updateActive((t) => ({
      ...t,
      updatedAt: Date.now(),
      messages: [...t.messages, msg],
    }));
  };

  const patchAssistant = (
    assistantId: string,
    patch: Partial<Message>,
  ) => {
    updateActive((t) => ({
      ...t,
      updatedAt: Date.now(),
      messages: t.messages.map((m) =>
        m.id === assistantId ? { ...m, ...patch } : m,
      ),
    }));
  };

  const handleSend = async (text: string) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const userMsg: Message = { id: crypto.randomUUID(), role: "user", content: text };
    const assistantId = crypto.randomUUID();

    updateActive((t) => ({
      ...t,
      title: t.messages.length === 0 ? titleFromMessage(text) : t.title,
      updatedAt: Date.now(),
      messages: [
        ...t.messages,
        userMsg,
        { id: assistantId, role: "assistant", content: "", streaming: true },
      ],
    }));

    setBusy(true);
    let sources: Source[] = [];
    let queryProfile = "general";
    let content = "";

    try {
      await streamChat(
        text,
        activeId,
        useLlm,
        (event) => {
          if (event.type === "meta") {
            sources = event.sources;
            queryProfile = event.query_profile;
          } else if (event.type === "token") {
            content += event.content;
            patchAssistant(assistantId, { content, streaming: true, sources, queryProfile });
          } else if (event.type === "error") {
            content += `\n\n⚠ ${event.message}`;
            patchAssistant(assistantId, { content, streaming: true });
          } else if (event.type === "done") {
            const final = event.answer || content || "(пустой ответ)";
            patchAssistant(assistantId, {
              content: final,
              streaming: false,
              sources,
              queryProfile,
            });
          }
        },
        controller.signal,
      );
      await refreshClaims();
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      patchAssistant(assistantId, {
        content: `Ошибка: ${e instanceof Error ? e.message : String(e)}`,
        streaming: false,
      });
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  };

  const handleUpload = async (file: File) => {
    appendMessage({
      id: crypto.randomUUID(),
      role: "system",
      content: `Загрузка ${file.name}…`,
    });
    setBusy(true);
    try {
      const res = await uploadFile(activeId, file);
      appendMessage({
        id: crypto.randomUUID(),
        role: "system",
        content: `Файл обработан: ${res.blocks} блоков, +${res.claims_added} фактов`,
      });
      await refreshClaims();
    } catch (e) {
      appendMessage({
        id: crypto.randomUUID(),
        role: "system",
        content: `Ошибка загрузки: ${e instanceof Error ? e.message : String(e)}`,
      });
    } finally {
      setBusy(false);
    }
  };

  const empty = activeThread.messages.length === 0;

  return (
    <div className="h-full flex bg-em-bg dark:bg-em-d-bg transition-colors">
      <Sidebar
        threads={threads}
        activeId={activeId}
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((v) => !v)}
        onSelect={setActiveId}
        onNew={createThread}
        onDelete={deleteThread}
      />

      <div className="flex-1 flex flex-col min-w-0 relative">
        <header className="h-14 flex items-center justify-between px-4 border-b border-em-border dark:border-em-d-border bg-em-bg/80 dark:bg-em-d-bg/80 backdrop-blur shrink-0">
          <div className="flex items-center gap-2 text-sm text-em-muted dark:text-em-d-muted">
            <Sparkles size={16} className="text-em-accent" />
            <span className="hidden sm:inline">Чат с памятью</span>
          </div>
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-2 text-xs text-em-muted dark:text-em-d-muted cursor-pointer select-none">
              <input
                type="checkbox"
                checked={useLlm}
                onChange={(e) => setUseLlm(e.target.checked)}
                className="rounded border-gray-300 dark:border-gray-600 text-em-accent focus:ring-em-accent"
              />
              LLM
            </label>
            <ThemeToggle theme={theme} onToggle={toggleTheme} />
            <button
              type="button"
              onClick={() => setMemoryOpen(true)}
              className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border border-em-border dark:border-em-d-border bg-white dark:bg-em-d-card hover:bg-gray-50 dark:hover:bg-em-d-hover dark:text-em-d-text"
            >
              <Brain size={16} />
              <span className="hidden sm:inline">Память</span>
              {claims.length > 0 && (
                <span className="text-xs bg-em-accent/10 text-em-accent px-1.5 rounded-full">
                  {claims.length}
                </span>
              )}
            </button>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto">
          {empty ? (
            <div className="max-w-2xl mx-auto px-4 flex flex-col items-center justify-center min-h-full py-12">
              <div className="mb-8 text-center">
                <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-em-accent text-white text-xl font-semibold mb-4">
                  e
                </div>
                <h1 className="text-2xl sm:text-3xl font-semibold text-em-text dark:text-em-d-text tracking-tight">
                  evermem
                </h1>
                <p className="text-em-muted dark:text-em-d-muted mt-2 text-sm">
                  Local-first память для ваших диалогов
                </p>
              </div>
              <ChatInput
                disabled={busy}
                variant="hero"
                onSend={handleSend}
                onUpload={handleUpload}
              />
              <div className="grid sm:grid-cols-2 gap-2 w-full mt-6">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    disabled={busy}
                    onClick={() => handleSend(s)}
                    className="text-left text-sm p-3 rounded-xl border border-em-border dark:border-em-d-border bg-white/80 dark:bg-em-d-card hover:border-em-accent/30 hover:bg-white dark:hover:bg-em-d-hover transition-all dark:text-em-d-text"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto px-4 py-8">
              {activeThread.messages.map((m) => (
                <ChatMessage
                  key={m.id}
                  message={m}
                  onFeedback={
                    m.role === "assistant" && !m.streaming
                      ? (h) => sendFeedback(activeId, h)
                      : undefined
                  }
                />
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </main>

        {!empty && (
          <ChatInput disabled={busy} onSend={handleSend} onUpload={handleUpload} />
        )}

        <MemoryPanel
          open={memoryOpen}
          onClose={() => setMemoryOpen(false)}
          claims={claims}
          loading={claimsLoading}
        />
      </div>
    </div>
  );
}
