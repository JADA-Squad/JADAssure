import { useState, type FormEvent } from "react";
import { Link, Navigate } from "react-router-dom";

import { ApiError } from "../../api/client";
import { useAuth, type SignupInput } from "./AuthContext";
import { Brand } from "../../components/Brand";

const BUSINESS_TYPES: [string, string][] = [
  ["professional_services", "Professional services"],
  ["subscription_software", "Subscription software"],
  ["distribution", "Distribution"],
  ["other", "Other"],
];

export function SignupPage() {
  const { session, signup } = useAuth();
  const [form, setForm] = useState<SignupInput>({
    organization_name: "",
    business_type: "other",
    name: "",
    email: "",
    password: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (session) return <Navigate to="/overview" replace />;

  const set = (key: keyof SignupInput) => (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signup(form);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <form className="card auth-card" onSubmit={submit}>
        <Brand />
        <p className="muted">Create an organization. You become its administrator.</p>
        <div className="field">
          <label htmlFor="org">Organization name</label>
          <input id="org" required value={form.organization_name} onChange={set("organization_name")} />
        </div>
        <div className="field">
          <label htmlFor="btype">Business type</label>
          <select id="btype" value={form.business_type} onChange={set("business_type")}>
            {BUSINESS_TYPES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="name">Your name</label>
          <input id="name" required autoComplete="name" value={form.name} onChange={set("name")} />
        </div>
        <div className="field">
          <label htmlFor="email">Email</label>
          <input id="email" type="email" required autoComplete="username" value={form.email} onChange={set("email")} />
        </div>
        <div className="field">
          <label htmlFor="password">Password (at least 10 characters)</label>
          <input
            id="password"
            type="password"
            required
            minLength={10}
            autoComplete="new-password"
            value={form.password}
            onChange={set("password")}
          />
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="btn primary" type="submit" disabled={busy}>
          {busy ? "Creating…" : "Create organization"}
        </button>
        <p className="auth-switch muted">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </form>
    </div>
  );
}
