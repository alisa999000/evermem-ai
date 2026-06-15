import { Moon, Sun } from "lucide-react";
import type { Theme } from "../hooks/useTheme";

type Props = {
  theme: Theme;
  onToggle: () => void;
};

export function ThemeToggle({ theme, onToggle }: Props) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="p-2 rounded-lg border border-em-border dark:border-em-d-border bg-white dark:bg-em-d-card hover:bg-gray-50 dark:hover:bg-em-d-hover text-em-muted dark:text-em-d-muted transition-colors"
      title={theme === "dark" ? "Светлая тема" : "Тёмная тема"}
    >
      {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}
