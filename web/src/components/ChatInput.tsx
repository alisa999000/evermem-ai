import { useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import { ArrowUp, Paperclip } from "lucide-react";

type Props = {
  disabled?: boolean;
  onSend: (text: string) => void;
  onUpload: (file: File) => void;
  variant?: "default" | "hero";
};

export function ChatInput({ disabled, onSend, onUpload, variant = "default" }: Props) {
  const [text, setText] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const hero = variant === "hero";

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div
      className={`${hero ? "w-full" : "max-w-3xl mx-auto w-full"} px-4 ${hero ? "pb-0" : "pb-6 pt-2"}`}
    >
      <div
        className={`relative rounded-2xl border border-em-border dark:border-em-d-border bg-white dark:bg-em-d-card shadow-em focus-within:border-em-accent/40 focus-within:shadow-md transition-shadow ${
          hero ? "shadow-md" : ""
        }`}
      >
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKey}
          disabled={disabled}
          rows={hero ? 2 : 1}
          placeholder="Спросите что угодно..."
          className={`w-full resize-none bg-transparent px-4 pt-4 pb-12 outline-none placeholder:text-em-muted dark:placeholder:text-em-d-muted dark:text-em-d-text ${
            hero ? "text-base min-h-[64px]" : "text-[15px] min-h-[52px] max-h-40"
          }`}
          style={{ fieldSizing: "content" } as CSSProperties}
        />
        <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between">
          <div>
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.txt,.md"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) onUpload(f);
                e.target.value = "";
              }}
            />
            <button
              type="button"
              disabled={disabled}
              onClick={() => fileRef.current?.click()}
              className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-em-d-hover text-em-muted dark:text-em-d-muted disabled:opacity-40"
              title="Загрузить PDF/текст"
            >
              <Paperclip size={18} />
            </button>
          </div>
          <button
            type="button"
            onClick={submit}
            disabled={disabled || !text.trim()}
            className="p-2 rounded-xl bg-em-accent text-white disabled:opacity-40 disabled:bg-gray-300 dark:disabled:bg-gray-600 hover:bg-teal-700 transition-colors"
            title="Отправить"
          >
            <ArrowUp size={18} />
          </button>
        </div>
      </div>
      {!hero && (
        <p className="text-center text-[11px] text-em-muted dark:text-em-d-muted mt-2">
          evermem может ошибаться. Проверяйте важные факты.
        </p>
      )}
    </div>
  );
}
