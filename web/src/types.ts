export type Claim = {
  subject: string;
  predicate: string;
  value: string;
  kind: string;
  trust: number;
  support: number;
};

export type Source = {
  id: number;
  type: "claim" | "turn" | "episode" | "event";
  title: string;
  snippet: string;
  session_id?: string;
  score?: number;
};

export type Message = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  sources?: Source[];
  streaming?: boolean;
  queryProfile?: string;
};

export type Thread = {
  id: string;
  title: string;
  updatedAt: number;
  messages: Message[];
};

export type ChatResponse = {
  session_id: string;
  answer: string;
  memory_prompt: string;
  query_profile: string;
  sources: Source[];
  llm_error: string;
};

export type StreamEvent =
  | { type: "session"; session_id: string }
  | { type: "meta"; memory_prompt: string; query_profile: string; sources: Source[] }
  | { type: "token"; content: string }
  | { type: "error"; message: string }
  | { type: "done"; answer: string; llm_error?: string };
