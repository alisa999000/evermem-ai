import type { ChatResponse, Claim, StreamEvent } from "./types";

const API_KEY = import.meta.env.VITE_EVERMEM_API_KEY ?? "";

function headers(): HeadersInit {
  const h: HeadersInit = { "Content-Type": "application/json" };
  if (API_KEY) h["X-API-Key"] = API_KEY;
  return h;
}

export async function fetchProfile(): Promise<Claim[]> {
  const r = await fetch("/api/profile", { headers: headers() });
  if (!r.ok) throw new Error("profile failed");
  const data = await r.json();
  return data.claims ?? [];
}

export async function sendChat(
  message: string,
  sessionId: string,
  useLlm: boolean,
): Promise<ChatResponse> {
  const r = await fetch("/api/chat", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ message, session_id: sessionId, use_llm: useLlm }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function streamChat(
  message: string,
  sessionId: string,
  useLlm: boolean,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const r = await fetch("/api/chat/stream", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ message, session_id: sessionId, use_llm: useLlm }),
    signal,
  });
  if (!r.ok) throw new Error(await r.text());

  const reader = r.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const payload = line.slice(6).trim();
      if (payload === "[DONE]") return;
      onEvent(JSON.parse(payload) as StreamEvent);
    }
  }
}

export async function sendFeedback(sessionId: string, helpful: boolean): Promise<void> {
  await fetch("/api/feedback", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ helpful, session_id: sessionId }),
  });
}

export async function uploadFile(
  sessionId: string,
  file: File,
): Promise<{ blocks: number; claims_added: number }> {
  const form = new FormData();
  form.append("file", file);
  form.append("session_id", sessionId);
  const h: HeadersInit = {};
  if (API_KEY) h["X-API-Key"] = API_KEY;
  const r = await fetch("/api/upload", { method: "POST", headers: h, body: form });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
