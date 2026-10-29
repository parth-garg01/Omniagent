import { useCallback, useEffect, useState } from "react";
import { api } from "./api/client";
import type { Conversation, User } from "./api/types";
import { AdminPanel } from "./features/admin/AdminPanel";
import { AuthForm } from "./features/auth/AuthForm";
import { ChatView } from "./features/chat/ChatView";
import { Sidebar } from "./features/chat/Sidebar";
import { KnowledgePanel } from "./features/knowledge/KnowledgePanel";

type Tab = "chat" | "knowledge" | "admin";

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("chat");

  useEffect(() => {
    api<User>("/auth/me").then(setUser).catch(() => {}).finally(() => setReady(true));
  }, []);

  const refresh = useCallback(() => {
    api<Conversation[]>("/conversations").then(setConvs).catch(() => {});
  }, []);
  useEffect(() => { if (user && user.role !== "evaluator") refresh(); }, [user, refresh]);
  useEffect(() => {
    if (user?.role === "evaluator") setTab("admin");
  }, [user]);

  async function logout() {
    await api("/auth/logout", { method: "POST" }).catch(() => {});
    setUser(null);
    setConvs([]);
    setActiveId(null);
  }

  if (!ready) return <main className="center muted">Loading…</main>;
  if (!user) return <main className="center"><AuthForm onAuthed={setUser} /></main>;

  const isEval = user.role === "evaluator";
  return (
    <div className="shell">
      <header>
        <strong>Nova</strong>
        <nav className="tabs">
          {!isEval && <button className={tab === "chat" ? "on" : ""} onClick={() => setTab("chat")}>Chat</button>}
          {!isEval && <button className={tab === "knowledge" ? "on" : ""} onClick={() => setTab("knowledge")}>Knowledge</button>}
          {(user.role === "admin" || isEval) && <button className={tab === "admin" ? "on" : ""} onClick={() => setTab("admin")}>Admin</button>}
        </nav>
        <span className="muted">{user.email} ({user.role})</span>
        <button className="secondary" onClick={logout}>Sign out</button>
      </header>
      {tab === "chat" && !isEval && (
        <div className="body">
          <Sidebar conversations={convs} activeId={activeId} onSelect={setActiveId} onChanged={refresh} />
          {activeId ? <ChatView key={activeId} conversationId={activeId} onChanged={refresh} /> : <div className="center muted">Select or create a conversation.</div>}
        </div>
      )}
      {tab === "knowledge" && !isEval && <KnowledgePanel isAdmin={user.role === "admin"} />}
      {tab === "admin" && <AdminPanel canRun={user.role === "admin"} />}
    </div>
  );
}
