import ReactMarkdown from "react-markdown";
import { Copy, ThumbsDown, ThumbsUp } from "lucide-react";
import { SourcesBlock } from "./SourcesBlock";
import type { Message } from "../types";

function LoadingDots() {
  return (
    <div className="flex gap-1 py-2">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="loading-dot w-2 h-2 rounded-full bg-em-muted dark:bg-em-d-muted"
        />
      ))}
    </div>
  );
}

type Props = {
  message: Message;
  onFeedback?: (helpful: boolean) => void;
};

export function ChatMessage({ message, onFeedback }: Props) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end mb-6">
        <div className="max-w-[85%] bg-em-user dark:bg-em-d-user rounded-2xl px-4 py-3 text-[15px] leading-relaxed">
          {message.content}
        </div>
      </div>
    );
  }

  if (message.role === "system") {
    return (
      <div className="text-center text-xs text-em-muted dark:text-em-d-muted mb-4">
        {message.content}
      </div>
    );
  }

  const showCursor = message.streaming && message.content;

  return (
    <div className="mb-8 group">
      <div className="flex items-start gap-3">
        <div className="w-7 h-7 rounded-full bg-em-accent text-white flex items-center justify-center text-xs font-semibold shrink-0 mt-0.5">
          e
        </div>
        <div className="flex-1 min-w-0">
          <div
            className={`markdown-body text-[15px] text-em-text dark:text-em-d-text ${
              showCursor ? "stream-cursor" : ""
            }`}
          >
            {message.content ? (
              <ReactMarkdown>{message.content}</ReactMarkdown>
            ) : (
              <LoadingDots />
            )}
          </div>

          {message.sources && message.sources.length > 0 && !message.streaming && (
            <SourcesBlock sources={message.sources} queryProfile={message.queryProfile} />
          )}

          {message.content && onFeedback && !message.streaming && (
            <div className="flex items-center gap-1 mt-3 opacity-0 group-hover:opacity-100 transition-opacity">
              <button
                type="button"
                onClick={() => onFeedback(true)}
                className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-em-d-hover text-em-muted dark:text-em-d-muted"
                title="Полезно"
              >
                <ThumbsUp size={16} />
              </button>
              <button
                type="button"
                onClick={() => onFeedback(false)}
                className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-em-d-hover text-em-muted dark:text-em-d-muted"
                title="Не полезно"
              >
                <ThumbsDown size={16} />
              </button>
              <button
                type="button"
                onClick={() => navigator.clipboard.writeText(message.content)}
                className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-em-d-hover text-em-muted dark:text-em-d-muted"
                title="Копировать"
              >
                <Copy size={16} />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
