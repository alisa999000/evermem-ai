import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDownIcon, CircleStackIcon } from "@heroicons/react/24/outline";
import { fetchProfile, sendChat, sendFeedback, streamChat, uploadFile } from "./api";
import { ChatInput } from "./components/ChatInput";
import { ChatMessage } from "./components/ChatMessage";
import { MemoryPanel } from "./components/MemoryPanel";
import { Sidebar } from "./components/Sidebar";
import { Switch } from "./components/Switch";
import { ThemeToggle } from "./components/ThemeToggle";
import { useTheme } from "./hooks/useTheme";
import { useThreads } from "./hooks/useThreads";
import type { Claim, Message, Source } from "./types";

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
  const [showScrollBtn, setShowScrollBtn] = useState(false);

  const mainRef = useRef<HTMLDivElement>(null);
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

  const scrollToBottom = useCallback((smooth = true) => {
    bottomRef.current?.scrollIntoView({ behavior: smooth ? "smooth" : "auto" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [activeThread.messages, busy, scrollToBottom]);

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const onMainScroll = () => {
    const el = mainRef.current;
    if (!el) return;
    const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
    setShowScrollBtn(dist > 120);
  };

  const appendMessage = (msg: Message) => {
    updateActive((t) => ({
      ...t,
      updatedAt: Date.now(),
      messages: [...t.messages, msg],
    }));
  };

  const patchAssistant = (assistantId: string, patch: Partial<Message>) => {
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
      } catch {
        const res = await sendChat(text, activeId, useLlm);
        sources = res.sources ?? [];
        queryProfile = res.query_profile;
        let answer = res.answer || res.memory_prompt || "(пустой ответ)";
        if (res.llm_error) answer += `\n\n⚠ ${res.llm_error}`;
        patchAssistant(assistantId, {
          content: answer,
          streaming: false,
          sources,
          queryProfile,
        });
      }
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
    <div className="h-full flex bg-em-bg dark:bg-em-d-bg">
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
        <header className="absolute top-0 inset-x-0 z-10 h-12 flex items-center justify-end px-3 gap-0.5 pointer-events-none">
          <div className="flex items-center gap-0.5 pointer-events-auto">
            <Switch checked={useLlm} onChange={setUseLlm} label="LLM" />
            <ThemeToggle theme={theme} onToggle={toggleTheme} />
            <button
              type="button"
              onClick={() => setMemoryOpen(true)}
              className="btn-icon relative"
              title="Память"
            >
              <CircleStackIcon className="w-5 h-5" strokeWidth={1.5} />
              {claims.length > 0 && (
                <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-em-accent" />
              )}
            </button>
          </div>
        </header>

        <main
          ref={mainRef}
          onScroll={onMainScroll}
          className="flex-1 min-h-0 overflow-y-auto pt-12"
        >
          {empty ? (
            <div className="h-full flex items-center justify-center pb-28">
              <h2 className="text-2xl font-normal text-em-text dark:text-em-d-text">
                Чем могу помочь?
              </h2>
            </div>
          ) : (
            <div className="chat-shell py-6">
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
              <div ref={bottomRef} className="h-4" />
            </div>
          )}
        </main>

        {showScrollBtn && !empty && (
          <button
            type="button"
            onClick={() => scrollToBottom()}
            className="absolute bottom-28 left-1/2 -translate-x-1/2 z-10 w-8 h-8 rounded-full bg-white dark:bg-em-d-card border border-em-border dark:border-white/10 shadow-md flex items-center justify-center text-em-muted dark:text-em-d-muted hover:bg-gray-50 dark:hover:bg-white/10 transition-all"
            title="Вниз"
          >
            <ChevronDownIcon className="w-4 h-4" strokeWidth={2} />
          </button>
        )}

        <footer className="shrink-0 bg-gradient-to-t from-em-bg via-em-bg dark:from-em-d-bg dark:via-em-d-bg to-transparent pt-2">
          <ChatInput
            disabled={busy}
            autoFocus={empty}
            onSend={handleSend}
            onUpload={handleUpload}
          />
        </footer>

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
