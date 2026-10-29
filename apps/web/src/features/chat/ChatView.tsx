import { useEffect, useRef, useState } from "react";
import { api, streamMessage } from "../../api/client";
import type { Citation, Msg, ToolEvent } from "../../api/types";
import { Markdown } from "../../components/Markdown";
import { CitationList } from "./CitationList";
import { ToolCard } from "./ToolCard";

export function ChatView({ conversationId, onChanged }: { conversationId: string; onChanged: () => void }) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [tools, setTools] = useState<ToolEvent[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");
  const abort = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  async function load() {
    const d = await api(`/conversations/${conversationId}`);
    setMessages(d.messages);
    setTools([]);
  }

  useEffect(() => {
    setError("");
    load().catch((e) => setError(e.message));
  }, [conversationId]);

  useEffect(() => bottom.current?.scrollIntoView?.({ behavior: "smooth" }), [messages, tools]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    setError("");
    setStreaming(true);
    abort.current = new AbortController();
    const draft: Msg = { id: "draft", role: "assistant", content: "", status: "streaming" };
    setMessages((m) => [...m, { id: "tmp", role: "user", content: text, status: "complete" }, draft]);
    try {
      await streamMessage(conversationId, text, (ev) => {
        if (ev.event === "delta") {
          setMessages((m) => m.map((x) => (x.id === "draft" ? { ...x, content: x.content + ev.data.text } : x)));
        } else if (ev.event === "tool_result") {
          setTools((t) => [...t, ev.data]);
        } else if (ev.event === "citations") {
          const citations: Citation[] = ev.data.citations;
          setMessages((m) => m.map((x) => (x.id === "draft" ? { ...x, citations } : x)));
        } else if (ev.event === "error") {
          setError(ev.data.message);
        }
      }, abort.current.signal);
    } catch (err) {
      if ((err as Error).name !== "AbortError") setError((err as Error).message);
    } finally {
      setStreaming(false);
      await load().catch(() => {});
      onChanged();
    }
  }

  async function stop() {
    await api(`/conversations/${conversationId}/cancel`, { method: "POST" }).catch(() => {});
  }

  async function rate(id: string, value: "up" | "down") {
    await api(`/messages/${id}/feedback`, { method: "POST", json: { value } }).catch(() => {});
    setMessages((m) => m.map((x) => (x.id === id ? { ...x, feedback: value } : x)));
  }

  return (
    <section className="chat">
      <div className="messages">
        {messages.map((m) => (
          <article key={m.id} className={`msg ${m.role}`}>
            <Markdown text={m.content || (m.status === "streaming" ? "…" : "")} />
            {m.status === "error" && <div className="error">This response failed.</div>}
            {m.status === "cancelled" && <div className="muted">Stopped.</div>}
            {m.citations && m.citations.length > 0 && <CitationList citations={m.citations} />}
            {m.role === "assistant" && m.status === "complete" && m.id !== "draft" && (
              <div className="row feedback">
                <button className="link" aria-pressed={m.feedback === "up"} onClick={() => rate(m.id, "up")}>👍</button>
                <button className="link" aria-pressed={m.feedback === "down"} onClick={() => rate(m.id, "down")}>👎</button>
              </div>
            )}
          </article>
        ))}
        {tools.map((t, i) => <ToolCard key={i} ev={t} onResolved={() => load().catch(() => {})} />)}
        <div ref={bottom} />
      </div>
      {error && <div className="error" role="alert">{error}</div>}
      <form className="composer" onSubmit={send}>
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask a question, e.g. “Where is ORD-1001?”" maxLength={4000} />
        {streaming ? <button type="button" onClick={stop}>Stop</button> : <button disabled={!input.trim()}>Send</button>}
      </form>
    </section>
  );
}
