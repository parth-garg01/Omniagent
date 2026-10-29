import { SseParser, type SseEvent } from "./sse";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function csrf(): string {
  const m = document.cookie.match(/(?:^|; )nova_csrf=([^;]*)/);
  return m ? decodeURIComponent(m[1]) : "";
}

export async function api<T = any>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  let body = init.body;
  if (init.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.json);
  }
  if ((init.method ?? "GET") !== "GET") headers["X-CSRF-Token"] = csrf();
  const res = await fetch(`/api/v1${path}`, { ...init, headers, body, credentials: "same-origin" });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : "Request failed";
    throw new ApiError(res.status, detail);
  }
  return data as T;
}

/** POST a chat message and surface streamed events via callback. */
export async function streamMessage(
  conversationId: string,
  content: string,
  onEvent: (e: SseEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`/api/v1/conversations/${conversationId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
    body: JSON.stringify({ content, client_message_id: crypto.randomUUID() }),
    credentials: "same-origin",
    signal,
  });
  if (!res.ok || !res.body) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(res.status, typeof data.detail === "string" ? data.detail : "Request failed");
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  const parser = new SseParser();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    parser.push(dec.decode(value, { stream: true })).forEach(onEvent);
  }
}
