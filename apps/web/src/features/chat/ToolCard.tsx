import { useState } from "react";
import { api } from "../../api/client";
import type { ToolEvent } from "../../api/types";

export function ToolCard({ ev, onResolved }: { ev: ToolEvent; onResolved: () => void }) {
  const [state, setState] = useState(ev.status);
  const [busy, setBusy] = useState(false);
  const pending = state === "pending_confirmation" && ev.execution_id;

  async function act(kind: "confirm" | "cancel") {
    setBusy(true);
    try {
      const r = await api(`/tool-executions/${ev.execution_id}/${kind}`, { method: "POST" });
      setState(r.status);
      onResolved();
    } catch {
      setState("failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`tool tool-${state}`}>
      <div><strong>{ev.name}</strong> <span className="badge">{state.replace("_", " ")}</span></div>
      <div className="muted">{ev.summary}</div>
      {pending && (
        <div className="row">
          <button disabled={busy} onClick={() => act("confirm")}>Confirm</button>
          <button disabled={busy} className="secondary" onClick={() => act("cancel")}>Cancel</button>
        </div>
      )}
    </div>
  );
}
