import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import type { DocumentInfo } from "../../api/types";

export function KnowledgePanel({ isAdmin }: { isAdmin: boolean }) {
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const [error, setError] = useState("");
  const [shared, setShared] = useState(false);
  const file = useRef<HTMLInputElement>(null);

  const load = () => api<DocumentInfo[]>("/documents").then(setDocs).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    const f = file.current?.files?.[0];
    if (!f) return;
    const form = new FormData();
    form.append("file", f);
    if (shared) form.append("shared", "true");
    setError("");
    try {
      await api("/documents", { method: "POST", body: form });
      if (file.current) file.current.value = "";
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }
  const act = (path: string, method: string) => api(path, { method }).then(load).catch((e) => setError(e.message));

  return (
    <section className="panel">
      <h2>Knowledge base</h2>
      <form className="row" onSubmit={upload}>
        <input ref={file} type="file" accept=".pdf,.txt,.md,.docx" />
        {isAdmin && <label className="inline"><input type="checkbox" checked={shared} onChange={(e) => setShared(e.target.checked)} /> share with everyone</label>}
        <button>Upload</button>
      </form>
      {error && <div className="error" role="alert">{error}</div>}
      <table>
        <thead><tr><th>File</th><th>Status</th><th>Chunks</th><th>Access</th><th /></tr></thead>
        <tbody>
          {docs.map((d) => (
            <tr key={d.id}>
              <td>{d.filename} <span className="muted">v{d.version}</span></td>
              <td>{d.ingestion_status}{d.error ? ` — ${d.error}` : ""}</td>
              <td>{d.chunk_count}</td>
              <td>{d.access_policy}</td>
              <td className="row">
                <button className="link" onClick={() => act(`/documents/${d.id}/reindex`, "POST")}>Reindex</button>
                <button className="link" onClick={() => act(`/documents/${d.id}`, "DELETE")}>Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
