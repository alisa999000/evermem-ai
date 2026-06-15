import { MessageSquarePlus, PanelLeftClose, PanelLeft, Trash2 } from "lucide-react";
import type { Thread } from "../types";

type Props = {
  threads: Thread[];
  activeId: string;
  collapsed: boolean;
  onToggle: () => void;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
};

export function Sidebar({
  threads,
  activeId,
  collapsed,
  onToggle,
  onSelect,
  onNew,
  onDelete,
}: Props) {
  return (
    <aside
      className={`${
        collapsed ? "w-0 md:w-14" : "w-64"
      } shrink-0 border-r border-em-border dark:border-em-d-border bg-em-sidebar dark:bg-em-d-sidebar flex flex-col transition-all duration-200 overflow-hidden`}
    >
      <div className="h-14 flex items-center justify-between px-3 border-b border-em-border dark:border-em-d-border shrink-0">
        {!collapsed && (
          <span className="font-semibold text-sm tracking-tight pl-1 dark:text-em-d-text">
            evermem
          </span>
        )}
        <button
          type="button"
          onClick={onToggle}
          className="p-2 rounded-lg hover:bg-gray-200/60 dark:hover:bg-em-d-hover text-em-muted dark:text-em-d-muted"
          title={collapsed ? "Показать меню" : "Скрыть меню"}
        >
          {collapsed ? <PanelLeft size={18} /> : <PanelLeftClose size={18} />}
        </button>
      </div>

      <div className="p-2 shrink-0">
        <button
          type="button"
          onClick={onNew}
          className={`w-full flex items-center gap-2 rounded-xl border border-em-border dark:border-em-d-border bg-white dark:bg-em-d-card hover:bg-gray-50 dark:hover:bg-em-d-hover text-sm font-medium transition-colors dark:text-em-d-text ${
            collapsed ? "justify-center p-2.5" : "px-3 py-2.5"
          }`}
        >
          <MessageSquarePlus size={18} />
          {!collapsed && <span>Новый чат</span>}
        </button>
      </div>

      {!collapsed && (
        <nav className="flex-1 overflow-y-auto px-2 pb-4">
          <p className="text-[11px] uppercase tracking-wider text-em-muted dark:text-em-d-muted px-2 py-2">
            Недавние
          </p>
          <ul className="space-y-0.5">
            {threads.map((t) => (
              <li key={t.id} className="group flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => onSelect(t.id)}
                  className={`flex-1 text-left text-sm truncate rounded-lg px-3 py-2 transition-colors ${
                    t.id === activeId
                      ? "bg-gray-200/70 dark:bg-em-d-hover text-em-text dark:text-em-d-text"
                      : "hover:bg-gray-100 dark:hover:bg-em-d-hover text-em-muted dark:text-em-d-muted"
                  }`}
                >
                  {t.title}
                </button>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(t.id);
                  }}
                  className="p-1.5 rounded-lg opacity-0 group-hover:opacity-100 hover:bg-gray-200 dark:hover:bg-em-d-hover text-em-muted dark:text-em-d-muted shrink-0"
                  title="Удалить"
                >
                  <Trash2 size={14} />
                </button>
              </li>
            ))}
          </ul>
        </nav>
      )}

      {!collapsed && (
        <div className="p-3 border-t border-em-border dark:border-em-d-border text-[11px] text-em-muted dark:text-em-d-muted shrink-0">
          Local-first memory · on-prem
        </div>
      )}
    </aside>
  );
}
