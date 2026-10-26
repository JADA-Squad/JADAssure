import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";

import { ApiError } from "../../api/client";
import { useAuth } from "./AuthContext";
import { DemoAccounts } from "./DemoAccounts";

export function LoginPage() {
  const { session, restoring, login } = useAuth();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (restoring) return <div className="auth-wrap muted">Loading…</div>;
  if (session) {
    const from = (location.state as { from?: string } | null)?.from ?? "/overview";
    return <Navigate to={from} replace />;
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap with-demo">
      <form className="card auth-card" onSubmit={submit}>
        <div className="brand">
          JAD<span>Assure</span>
        </div>
        <p className="muted">Sign in to your organization.</p>
        <div className="field">
          <label htmlFor="email">Email</label>
          <input id="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="btn primary" type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <p className="auth-switch muted">
          New organization? <Link to="/signup">Create one</Link>
        </p>
      </form>
      <DemoAccounts
        onPick={(pickedEmail, pickedPassword) => {
          setEmail(pickedEmail);
          setPassword(pickedPassword);
        }}
      />
    </div>
  );
}
