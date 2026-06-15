import { Brain, X } from "lucide-react";
import type { Claim } from "../types";

type Props = {
  open: boolean;
  onClose: () => void;
  claims: Claim[];
  loading: boolean;
};

export function MemoryPanel({ open, onClose, claims, loading }: Props) {
  if (!open) return null;

  return (
    <>
      <div className="fixed inset-0 bg-black/20 z-40 md:hidden" onClick={onClose} aria-hidden />
      <aside
        className="fixed md:absolute right-0 top-0 bottom-0 w-full max-w-sm bg-white dark:bg-em-d-card border-l border-em-border dark:border-em-d-border z-50 flex flex-col shadow-xl md:shadow-none"
        aria-label="Память"
      >
        <div className="flex items-center justify-between px-4 h-14 border-b border-em-border dark:border-em-d-border">
          <div className="flex items-center gap-2 font-medium text-sm dark:text-em-d-text">
            <Brain size={18} className="text-em-accent" />
            Память
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-em-d-hover"
          >
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          {loading && (
            <p className="text-sm text-em-muted dark:text-em-d-muted">Загрузка...</p>
          )}
          {!loading && claims.length === 0 && (
            <p className="text-sm text-em-muted dark:text-em-d-muted">
              Пока нет сохранённых фактов.
            </p>
          )}
          <ul className="space-y-3">
            {claims.map((c, i) => (
              <li
                key={`${c.predicate}-${c.value}-${i}`}
                className="text-sm p-3 rounded-xl bg-em-bg dark:bg-em-d-bg border border-em-border dark:border-em-d-border"
              >
                <div className="font-medium text-em-text dark:text-em-d-text truncate">
                  {c.subject} · {c.predicate}
                </div>
                <div className="text-em-muted dark:text-em-d-muted mt-1 break-words">
                  {c.value}
                </div>
                <div className="text-xs text-em-muted dark:text-em-d-muted mt-2">
                  trust {c.trust} · ×{c.support}
                </div>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </>
  );
}
