import { useState } from "react";
import {
  CalendarDaysIcon,
  ChatBubbleLeftIcon,
  ChevronDownIcon,
  DocumentTextIcon,
  SparklesIcon,
} from "@heroicons/react/24/outline";
import type { Source } from "../types";

const TYPE_LABEL: Record<Source["type"], string> = {
  claim: "Факт",
  turn: "Диалог",
  episode: "Эпизод",
  event: "Событие",
};

const TYPE_ICON: Record<Source["type"], typeof SparklesIcon> = {
  claim: SparklesIcon,
  turn: ChatBubbleLeftIcon,
  episode: DocumentTextIcon,
  event: CalendarDaysIcon,
};

type Props = {
  sources: Source[];
  queryProfile?: string;
};

export function SourcesBlock({ sources, queryProfile }: Props) {
  const [open, setOpen] = useState(false);
  if (!sources.length) return null;

  return (
    <div className="mt-3">
      <div className="flex flex-wrap items-center gap-1.5 mb-2">
        {sources.slice(0, 6).map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setOpen(true)}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs
              bg-black/[0.04] dark:bg-white/[0.06]
              text-em-muted dark:text-em-d-muted
              hover:bg-black/[0.07] dark:hover:bg-white/[0.1]
              transition-colors"
            title={s.snippet}
          >
            <span className="font-semibold text-em-text dark:text-em-d-text">{s.id}</span>
            <span className="truncate max-w-[120px]">{s.title.split("·").pop()?.trim() ?? s.title}</span>
          </button>
        ))}
      </div>

      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 text-xs text-em-muted dark:text-em-d-muted hover:text-em-text dark:hover:text-em-d-text transition-colors"
      >
        <ChevronDownIcon
          className={`w-3.5 h-3.5 transition-transform ${open ? "rotate-180" : ""}`}
          strokeWidth={2}
        />
        Источники · {sources.length}
        {queryProfile && queryProfile !== "general" && (
          <span className="opacity-60">({queryProfile})</span>
        )}
      </button>

      {open && (
        <ul className="mt-2 space-y-1">
          {sources.map((s) => {
            const Icon = TYPE_ICON[s.type];
            return (
              <li
                key={s.id}
                className="flex gap-2.5 p-3 rounded-xl bg-black/[0.03] dark:bg-white/[0.04] text-sm"
              >
                <span className="shrink-0 w-5 h-5 rounded-full text-[10px] font-bold bg-black/[0.06] dark:bg-white/[0.08] flex items-center justify-center">
                  {s.id}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1 text-[11px] text-em-muted dark:text-em-d-muted mb-0.5">
                    <Icon className="w-3 h-3" strokeWidth={1.75} />
                    <span>{TYPE_LABEL[s.type]}</span>
                    {s.score != null && <span>{Math.round(s.score * 100)}%</span>}
                  </div>
                  <p className="font-medium truncate">{s.title}</p>
                  <p className="text-em-muted dark:text-em-d-muted text-xs mt-0.5 line-clamp-2">{s.snippet}</p>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
