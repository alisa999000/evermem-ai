import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { ArrowUpIcon, PlusIcon } from "@heroicons/react/24/outline";

type Props = {
  disabled?: boolean;
  autoFocus?: boolean;
  onSend: (text: string) => void;
  onUpload: (file: File) => void;
};

export function ChatInput({ disabled, autoFocus, onSend, onUpload }: Props) {
  const [text, setText] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const canSend = text.trim().length > 0 && !disabled;

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [text]);

  useEffect(() => {
    if (autoFocus) textareaRef.current?.focus();
  }, [autoFocus]);

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="chat-shell pb-3 pt-1">
      <div className="input-pill">
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.txt,.md,.docx,.html"
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
          className="btn-icon shrink-0 mb-0.5"
          title="Прикрепить файл"
        >
          <PlusIcon className="w-5 h-5" strokeWidth={1.5} />
        </button>

        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKey}
          disabled={disabled}
          rows={1}
          placeholder="Спросите что-нибудь…"
          className="flex-1 resize-none bg-transparent outline-none py-2.5 px-1 text-[15px] leading-relaxed min-h-[24px] max-h-[200px] dark:text-em-d-text placeholder:text-em-muted/60 dark:placeholder:text-em-d-muted/60"
        />

        <button
          type="button"
          onClick={submit}
          disabled={!canSend}
          className={`
            shrink-0 mb-0.5 w-8 h-8 rounded-full flex items-center justify-center transition-all duration-150
            ${canSend
              ? "bg-em-text dark:bg-white text-white dark:text-black hover:opacity-90"
              : "bg-transparent text-em-muted/30 dark:text-em-d-muted/30"
            }
            disabled:pointer-events-none
          `}
          title="Отправить"
        >
          <ArrowUpIcon className="w-4 h-4" strokeWidth={2.5} />
        </button>
      </div>
      <p className="text-center text-[11px] text-em-muted/60 dark:text-em-d-muted/50 mt-2">
        evermem может ошибаться · проверяйте важные факты
      </p>
    </div>
  );
}
