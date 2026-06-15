import {
  Bars3Icon,
  PlusIcon,
  TrashIcon,
} from "@heroicons/react/24/outline";
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
      className={`
        shrink-0 bg-em-sidebar dark:bg-em-d-sidebar flex flex-col overflow-hidden
        transition-[width] duration-200
        ${collapsed ? "w-14" : "w-[260px]"}
      `}
    >
      <div
        className={`p-2 shrink-0 flex gap-1 ${collapsed ? "flex-col items-center" : "flex-row items-center"}`}
      >
        {collapsed ? (
          <>
            <button type="button" onClick={onToggle} className="btn-icon" title="Показать меню">
              <Bars3Icon className="w-5 h-5" strokeWidth={1.5} />
            </button>
            <button type="button" onClick={onNew} className="btn-icon" title="Новый чат">
              <PlusIcon className="w-5 h-5" strokeWidth={1.5} />
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              onClick={onNew}
              className="flex-1 flex items-center gap-2.5 rounded-lg text-sm px-3 py-2.5
                hover:bg-black/[0.05] dark:hover:bg-white/[0.06]
                transition-colors dark:text-em-d-text"
            >
              <PlusIcon className="w-5 h-5 shrink-0" strokeWidth={1.5} />
              <span>Новый чат</span>
            </button>
            <button type="button" onClick={onToggle} className="btn-icon shrink-0" title="Скрыть">
              <Bars3Icon className="w-5 h-5" strokeWidth={1.5} />
            </button>
          </>
        )}
      </div>

      {!collapsed && (
        <nav className="flex-1 overflow-y-auto px-2 pb-3">
          <p className="text-[11px] font-medium text-em-muted/70 dark:text-em-d-muted/70 px-3 py-2">
            Чаты
          </p>
          <ul className="space-y-0.5">
            {threads.map((t) => {
              const active = t.id === activeId;
              return (
                <li key={t.id} className="group flex items-center">
                  <button
                    type="button"
                    onClick={() => onSelect(t.id)}
                    className={`
                      flex-1 text-left text-sm truncate rounded-lg px-3 py-2
                      transition-colors duration-150
                      ${active
                        ? "bg-black/[0.06] dark:bg-white/[0.08] text-em-text dark:text-em-d-text"
                        : "text-em-muted dark:text-em-d-muted hover:bg-black/[0.04] dark:hover:bg-white/[0.05]"
                      }
                    `}
                  >
                    {t.title}
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(t.id)}
                    className="p-1.5 rounded-lg opacity-0 group-hover:opacity-100 hover:text-red-500 text-em-muted transition-all"
                    title="Удалить"
                  >
                    <TrashIcon className="w-4 h-4" strokeWidth={1.5} />
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>
      )}
    </aside>
  );
}
