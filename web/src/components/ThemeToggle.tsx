import { MoonIcon, SunIcon } from "@heroicons/react/24/outline";
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
      className="btn-icon"
      title={theme === "dark" ? "Светлая тема" : "Тёмная тема"}
    >
      {theme === "dark" ? (
        <SunIcon className="w-[18px] h-[18px]" strokeWidth={1.5} />
      ) : (
        <MoonIcon className="w-[18px] h-[18px]" strokeWidth={1.5} />
      )}
    </button>
  );
}
