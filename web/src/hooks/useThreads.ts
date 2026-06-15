import { useCallback, useEffect, useState } from "react";
import type { Thread } from "./types";

const STORAGE_KEY = "evermem_threads_v1";

function loadThreads(): Thread[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Thread[]) : [];
  } catch {
    return [];
  }
}

function saveThreads(threads: Thread[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(threads.slice(0, 40)));
}

export function newThreadId() {
  return `web-${crypto.randomUUID().slice(0, 12)}`;
}

export function useThreads() {
  const [threads, setThreads] = useState<Thread[]>(() => loadThreads());
  const [activeId, setActiveId] = useState<string>(() => threads[0]?.id ?? newThreadId());

  useEffect(() => {
    saveThreads(threads);
  }, [threads]);

  const activeThread =
    threads.find((t) => t.id === activeId) ??
    ({
      id: activeId,
      title: "Новый чат",
      updatedAt: Date.now(),
      messages: [],
    } satisfies Thread);

  const ensureThread = useCallback(() => {
    if (!threads.find((t) => t.id === activeId)) {
      setThreads((prev) => [
        { id: activeId, title: "Новый чат", updatedAt: Date.now(), messages: [] },
        ...prev,
      ]);
    }
  }, [activeId, threads]);

  useEffect(() => {
    ensureThread();
  }, [ensureThread]);

  const updateActive = useCallback(
    (updater: (t: Thread) => Thread) => {
      setThreads((prev) => {
        const idx = prev.findIndex((t) => t.id === activeId);
        if (idx === -1) {
          const created = updater(activeThread);
          return [created, ...prev];
        }
        const next = [...prev];
        next[idx] = updater(next[idx]);
        next.sort((a, b) => b.updatedAt - a.updatedAt);
        return next;
      });
    },
    [activeId, activeThread],
  );

  const createThread = () => {
    const id = newThreadId();
    const t: Thread = { id, title: "Новый чат", updatedAt: Date.now(), messages: [] };
    setThreads((prev) => [t, ...prev]);
    setActiveId(id);
  };

  const deleteThread = (id: string) => {
    setThreads((prev) => prev.filter((t) => t.id !== id));
    if (activeId === id) {
      const rest = threads.filter((t) => t.id !== id);
      setActiveId(rest[0]?.id ?? newThreadId());
    }
  };

  return {
    threads,
    activeThread,
    activeId,
    setActiveId,
    updateActive,
    createThread,
    deleteThread,
  };
}
