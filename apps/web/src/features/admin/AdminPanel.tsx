import { useEffect, useState } from "react";
import { api } from "../../api/client";

type Run = { id: string; dataset_name: string; created_at: string; metrics: Record<string, any> };

export function AdminPanel({ canRun }: { canRun: boolean }) {
  const [metrics, setMetrics] = useState<any>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState("");

  const load = () => {
    if (canRun) api("/admin/metrics").then(setMetrics).catch((e) => setError(e.message));
    api<Run[]>("/admin/evaluations").then(setRuns).catch((e) => setError(e.message));
  };
  useEffect(load, []);

  async function run(dataset: string) {
    setError("");
    try { await api("/admin/evaluations", { method: "POST", json: { dataset } }); load(); }
    catch (e) { setError((e as Error).message); }
  }

  return (
    <section className="panel">
      <h2>Observability &amp; evaluation</h2>
      {error && <div className="error" role="alert">{error}</div>}
      {metrics && (
        <dl className="stats">
          <div><dt>Responses</dt><dd>{metrics.responses}</dd></div>
          <div><dt>Error rate</dt><dd>{(metrics.error_rate * 100).toFixed(1)}%</dd></div>
          <div><dt>p50 / p95 ms</dt><dd>{metrics.latency_ms.p50 ?? "–"} / {metrics.latency_ms.p95 ?? "–"}</dd></div>
          <div><dt>Tokens in/out</dt><dd>{metrics.tokens.input} / {metrics.tokens.output}</dd></div>
        </dl>
      )}
      {canRun && <div className="row"><button onClick={() => run("rag")}>Run RAG eval</button><button onClick={() => run("tools")}>Run tool eval</button></div>}
      <table>
        <thead><tr><th>Dataset</th><th>When</th><th>Metrics</th></tr></thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id}>
              <td>{r.dataset_name}</td>
              <td>{new Date(r.created_at).toLocaleString()}</td>
              <td><code>{Object.entries(r.metrics).filter(([, v]) => typeof v === "number").map(([k, v]) => `${k}=${v}`).join("  ")}</code></td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
