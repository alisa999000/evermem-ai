import { useState } from "react";
import { ChevronDown, FileText, MessageCircle, Sparkles, Calendar } from "lucide-react";
import type { Source } from "../types";

const TYPE_LABEL: Record<Source["type"], string> = {
  claim: "Факт",
  turn: "Диалог",
  episode: "Эпизод",
  event: "Событие",
};

const TYPE_ICON: Record<Source["type"], typeof FileText> = {
  claim: Sparkles,
  turn: MessageCircle,
  episode: FileText,
  event: Calendar,
};

type Props = {
  sources: Source[];
  queryProfile?: string;
};

export function SourcesBlock({ sources, queryProfile }: Props) {
  const [open, setOpen] = useState(false);
  if (!sources.length) return null;

  return (
    <div className="mt-4 border-t border-em-border dark:border-em-d-border pt-3">
      <div className="flex flex-wrap gap-1.5 mb-2">
        {sources.slice(0, 8).map((s) => (
          <span
            key={s.id}
            className="inline-flex items-center justify-center min-w-[1.5rem] h-6 px-1.5 text-xs font-medium rounded-md bg-em-accent/10 dark:bg-em-accent/20 text-em-accent"
          >
            {s.id}
          </span>
        ))}
      </div>

      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 text-sm font-medium text-em-text dark:text-em-d-text hover:text-em-accent transition-colors"
      >
        <ChevronDown
          size={16}
          className={`transition-transform ${open ? "rotate-180" : ""}`}
        />
        Источники · {sources.length}
        {queryProfile && queryProfile !== "general" && (
          <span className="text-xs font-normal text-em-muted dark:text-em-d-muted">
            ({queryProfile})
          </span>
        )}
      </button>

      {open && (
        <ul className="mt-3 space-y-2">
          {sources.map((s) => {
            const Icon = TYPE_ICON[s.type];
            return (
              <li
                key={s.id}
                className="flex gap-3 p-3 rounded-xl border border-em-border dark:border-em-d-border bg-em-bg dark:bg-em-d-bg hover:border-em-accent/30 transition-colors"
              >
                <span className="shrink-0 w-6 h-6 rounded-md bg-em-accent/10 dark:bg-em-accent/20 text-em-accent text-xs font-semibold flex items-center justify-center">
                  {s.id}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 text-xs text-em-muted dark:text-em-d-muted mb-1">
                    <Icon size={12} />
                    <span>{TYPE_LABEL[s.type]}</span>
                    {s.session_id && (
                      <span className="truncate">· {s.session_id}</span>
                    )}
                    {s.score != null && (
                      <span>· {Math.round(s.score * 100)}%</span>
                    )}
                  </div>
                  <div className="text-sm font-medium text-em-text dark:text-em-d-text truncate">
                    {s.title}
                  </div>
                  <p className="text-sm text-em-muted dark:text-em-d-muted mt-1 line-clamp-3">
                    {s.snippet}
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
