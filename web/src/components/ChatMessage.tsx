import { useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import {
  CheckIcon,
  ClipboardDocumentIcon,
  HandThumbDownIcon,
  HandThumbUpIcon,
} from "@heroicons/react/24/outline";
import { SourcesBlock } from "./SourcesBlock";
import type { Message } from "../types";

function LoadingDots() {
  return (
    <div className="flex gap-1 py-4">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="loading-dot w-1.5 h-1.5 rounded-full bg-em-muted/50 dark:bg-em-d-muted/50"
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
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (message.role === "user") {
    return (
      <div className="flex justify-end mb-6">
        <div className="max-w-[85%] rounded-[1.25rem] bg-em-user dark:bg-em-d-user px-4 py-3 text-[15px] leading-relaxed dark:text-em-d-text">
          {message.content}
        </div>
      </div>
    );
  }

  if (message.role === "system") {
    return (
      <div className="flex justify-center mb-4">
        <span className="text-xs text-em-muted dark:text-em-d-muted">{message.content}</span>
      </div>
    );
  }

  const showCursor = message.streaming && message.content;

  return (
    <div className="mb-8">
      <div
        className={`markdown-body text-[15px] dark:text-em-d-text ${
          showCursor ? "stream-cursor" : ""
        }`}
      >
        {message.content ? (
          <ReactMarkdown>{message.content}</ReactMarkdown>
        ) : (
          <LoadingDots />
        )}
      </div>

      {!message.streaming && message.content && (
        <div className="flex flex-wrap items-center gap-1 mt-3 -ml-1">
          <ActionBtn
            onClick={copy}
            title={copied ? "Скопировано" : "Копировать"}
            icon={
              copied ? (
                <CheckIcon className="w-4 h-4" strokeWidth={2} />
              ) : (
                <ClipboardDocumentIcon className="w-4 h-4" strokeWidth={1.5} />
              )
            }
          />
          {onFeedback && (
            <>
              <ActionBtn
                onClick={() => onFeedback(true)}
                title="Полезно"
                icon={<HandThumbUpIcon className="w-4 h-4" strokeWidth={1.5} />}
              />
              <ActionBtn
                onClick={() => onFeedback(false)}
                title="Не полезно"
                icon={<HandThumbDownIcon className="w-4 h-4" strokeWidth={1.5} />}
              />
            </>
          )}
        </div>
      )}

      {message.sources && message.sources.length > 0 && !message.streaming && (
        <SourcesBlock sources={message.sources} queryProfile={message.queryProfile} />
      )}
    </div>
  );
}

function ActionBtn({
  onClick,
  title,
  icon,
}: {
  onClick: () => void;
  title: string;
  icon: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className="btn-icon !p-2 text-em-muted dark:text-em-d-muted"
    >
      {icon}
    </button>
  );
}
