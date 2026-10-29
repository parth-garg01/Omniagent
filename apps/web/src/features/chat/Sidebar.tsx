import { api } from "../../api/client";
import type { Conversation } from "../../api/types";

type Props = {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onChanged: () => void;
};

export function Sidebar({ conversations, activeId, onSelect, onChanged }: Props) {
  async function create() {
    const c = await api<Conversation>("/conversations", { method: "POST" });
    onChanged();
    onSelect(c.id);
  }
  async function rename(c: Conversation) {
    const title = window.prompt("Rename conversation", c.title);
    if (title?.trim()) {
      await api(`/conversations/${c.id}`, { method: "PATCH", json: { title: title.trim() } });
      onChanged();
    }
  }
  async function remove(c: Conversation) {
    if (!window.confirm("Delete this conversation?")) return;
    await api(`/conversations/${c.id}`, { method: "DELETE" });
    onChanged();
  }
  return (
    <nav className="sidebar" aria-label="Conversations">
      <button onClick={create}>+ New chat</button>
      <ul>
        {conversations.map((c) => (
          <li key={c.id} className={c.id === activeId ? "active" : ""}>
            <button className="link title" onClick={() => onSelect(c.id)}>{c.title}</button>
            <button className="link" aria-label="Rename" onClick={() => rename(c)}>✎</button>
            <button className="link" aria-label="Delete" onClick={() => remove(c)}>🗑</button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
