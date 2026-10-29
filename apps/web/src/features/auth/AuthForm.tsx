import { useState } from "react";
import { api } from "../../api/client";
import type { User } from "../../api/types";

export function AuthForm({ onAuthed }: { onAuthed: (u: User) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (mode === "register") await api("/auth/register", { method: "POST", json: { email, password } });
      onAuthed(await api<User>("/auth/login", { method: "POST", json: { email, password } }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="auth" onSubmit={submit}>
      <h1>Nova</h1>
      <p className="muted">Demo with synthetic data. Try alice@example.com / demo-password-1 after seeding.</p>
      <label>Email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
      <label>Password<input type="password" value={password} minLength={mode === "register" ? 8 : undefined} onChange={(e) => setPassword(e.target.value)} required /></label>
      {error && <div className="error" role="alert">{error}</div>}
      <button disabled={busy}>{mode === "login" ? "Sign in" : "Create account"}</button>
      <button type="button" className="link" onClick={() => setMode(mode === "login" ? "register" : "login")}>
        {mode === "login" ? "Need an account? Register" : "Have an account? Sign in"}
      </button>
    </form>
  );
}
