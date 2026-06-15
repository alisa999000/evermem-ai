import { useEffect, useState } from "react";
import { CircleStackIcon, XMarkIcon } from "@heroicons/react/24/outline";
import type { Claim } from "../types";

type Props = {
  open: boolean;
  onClose: () => void;
  claims: Claim[];
  loading: boolean;
};

export function MemoryPanel({ open, onClose, claims, loading }: Props) {
  const [mounted, setMounted] = useState(open);

  useEffect(() => {
    if (open) setMounted(true);
  }, [open]);

  if (!mounted) return null;

  return (
    <>
      <div
        className={`fixed inset-0 z-40 bg-black/20 transition-opacity duration-200 ${
          open ? "opacity-100" : "opacity-0 pointer-events-none"
        }`}
        onClick={onClose}
        aria-hidden
      />
      <aside
        className={`
          fixed md:absolute right-0 top-0 bottom-0 z-50 w-full max-w-sm
          bg-white dark:bg-em-d-card border-l border-em-border dark:border-em-d-border
          flex flex-col transition-transform duration-200 ease-out
          ${open ? "translate-x-0" : "translate-x-full"}
        `}
        onTransitionEnd={() => { if (!open) setMounted(false); }}
      >
        <div className="flex items-center justify-between px-4 h-12 border-b border-em-border dark:border-em-d-border shrink-0">
          <div className="flex items-center gap-2 text-sm font-medium dark:text-em-d-text">
            <CircleStackIcon className="w-5 h-5 text-em-accent" strokeWidth={1.5} />
            Память
            {claims.length > 0 && (
              <span className="text-xs text-em-muted dark:text-em-d-muted">{claims.length}</span>
            )}
          </div>
          <button type="button" onClick={onClose} className="btn-icon">
            <XMarkIcon className="w-5 h-5" strokeWidth={1.5} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {loading && (
            <p className="text-sm text-em-muted dark:text-em-d-muted">Загрузка…</p>
          )}
          {!loading && claims.length === 0 && (
            <p className="text-sm text-em-muted dark:text-em-d-muted text-center py-12">
              Нет сохранённых фактов
            </p>
          )}
          <ul className="space-y-2">
            {claims.map((c, i) => (
              <li
                key={`${c.predicate}-${c.value}-${i}`}
                className="p-3 rounded-lg border border-em-border dark:border-em-d-border text-sm"
              >
                <p className="font-medium text-em-text dark:text-em-d-text truncate">
                  {c.subject} · {c.predicate}
                </p>
                <p className="text-em-muted dark:text-em-d-muted mt-1 break-words">{c.value}</p>
                <p className="text-xs text-em-muted/70 dark:text-em-d-muted/70 mt-2">
                  trust {Math.round(c.trust * 100)}% · ×{c.support}
                </p>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </>
  );
}
