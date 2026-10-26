import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";

import { api, ApiError } from "../../api/client";
import type { User } from "../../api/types";
import { ROLE_LABELS, type Role } from "../../app/nav";
import { useAuth } from "../auth/AuthContext";

interface OrgSettings {
  organization_name: string;
  short_code: string;
  is_demo: boolean;
  refresh_interval_minutes: number;
  ai_provider: "stub" | "anthropic";
  ai_external_available: boolean;
  retention_days: number | null;
}

interface AuditEvent {
  seq: number;
  actor_id: string | null;
  action: string;
  entity: string;
  entity_id: string | null;
  payload: Record<string, unknown>;
  occurred_at: string;
  hash: string;
}

/** Access & settings (FR-38, FR-41): users and roles, org settings, audit history, data deletion. */
export function SettingsPage() {
  const { session } = useAuth();
  const caps = session?.me.capabilities ?? [];
  return (
    <div className="stack">
      <div className="page-header" style={{ marginBottom: 0 }}>
        <h1>Access &amp; settings</h1>
        <p className="muted">Who can do what, how the organization runs, and a tamper-evident record of every change.</p>
      </div>
      {caps.includes("manage_users_settings") && <UsersCard />}
      {caps.includes("manage_users_settings") && <OrgSettingsCard />}
      {caps.includes("view_audit") && <AuditCard />}
      {caps.includes("manage_users_settings") && <DangerZone />}
    </div>
  );
}

function UsersCard() {
  const { session } = useAuth();
  const qc = useQueryClient();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<User[]>("/users") });
  const [form, setForm] = useState({ name: "", email: "", role: "analyst" as Role, password: "" });
  const [error, setError] = useState<string | null>(null);
  const done = () => {
    setError(null);
    qc.invalidateQueries({ queryKey: ["users"] });
  };
  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : "The change failed");
  const create = useMutation({
    mutationFn: () => api<User>("/users", { method: "POST", body: JSON.stringify(form) }),
    onSuccess: () => {
      setForm({ name: "", email: "", role: "analyst", password: "" });
      done();
    },
    onError: fail,
  });
  const update = useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Partial<Pick<User, "role" | "active">> }) =>
      api<User>(`/users/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
    onSuccess: done,
    onError: fail,
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    create.mutate();
  }

  return (
    <section className="card stack" aria-label="Users">
      <h2 style={{ margin: 0 }}>Users &amp; roles</h2>
      <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>
            <th>Name</th>
            <th>Email</th>
            <th>Role</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {(users.data ?? []).map((u) => {
            const self = u.id === session?.me.user.id;
            return (
              <tr key={u.id}>
                <td>
                  {u.name}
                  {self && <span className="muted"> (you)</span>}
                </td>
                <td className="mono">{u.email}</td>
                <td>
                  <select
                    aria-label={`Role for ${u.name}`}
                    value={u.role}
                    disabled={self || update.isPending}
                    onChange={(e) => update.mutate({ id: u.id, patch: { role: e.target.value as Role } })}
                  >
                    {Object.entries(ROLE_LABELS).map(([r, label]) => (
                      <option key={r} value={r}>
                        {label}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <label className="row" style={{ gap: 6 }}>
                    <input
                      type="checkbox"
                      checked={u.active}
                      disabled={self || update.isPending}
                      onChange={(e) => update.mutate({ id: u.id, patch: { active: e.target.checked } })}
                    />
                    {u.active ? "Active" : "Deactivated"}
                  </label>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      </div>
      <form className="row" onSubmit={submit} aria-label="Add a user">
        <input aria-label="Name" placeholder="Name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input
          aria-label="Email"
          placeholder="Email"
          type="email"
          required
          value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
        />
        <select aria-label="Role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
          {Object.entries(ROLE_LABELS).map(([r, label]) => (
            <option key={r} value={r}>
              {label}
            </option>
          ))}
        </select>
        <input
          aria-label="Initial password"
          placeholder="Initial password (10+ characters)"
          type="password"
          minLength={10}
          required
          autoComplete="new-password"
          value={form.password}
          onChange={(e) => setForm({ ...form, password: e.target.value })}
        />
        <button className="btn primary" type="submit" disabled={create.isPending}>
          Add user
        </button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

function OrgSettingsCard() {
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api<OrgSettings>("/settings") });
  const [interval, setInterval_] = useState("0");
  const [provider, setProvider] = useState<"stub" | "anthropic">("stub");
  const [retention, setRetention] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const s = settings.data;
  useEffect(() => {
    if (!s) return;
    setInterval_(String(s.refresh_interval_minutes));
    setProvider(s.ai_provider);
    setRetention(s.retention_days ? String(s.retention_days) : "");
  }, [s]);
  const save = useMutation({
    mutationFn: () =>
      api<OrgSettings>("/settings", {
        method: "PUT",
        body: JSON.stringify({
          refresh_interval_minutes: Number(interval || 0),
          ai_provider: provider,
          ...(retention ? { retention_days: Number(retention) } : { clear_retention: true }),
        }),
      }),
    onSuccess: (data) => {
      qc.setQueryData(["settings"], data);
      qc.invalidateQueries({ queryKey: ["audit"] });
      setMsg({ ok: true, text: "Settings saved." });
    },
    onError: (e) => setMsg({ ok: false, text: e instanceof ApiError ? e.message : "Could not save" }),
  });
  if (!s) return null;

  return (
    <section className="card stack" aria-label="Organization settings">
      <h2 style={{ margin: 0 }}>
        Organization · {s.organization_name} <span className="muted mono">{s.short_code}</span>{" "}
        {s.is_demo && <span className="badge demo">DEMO</span>}
      </h2>
      <div className="settings-grid">
        <label className="field">
          <span>Scheduled check runs</span>
          <select value={interval} onChange={(e) => setInterval_(e.target.value)}>
            <option value="0">Off (run checks manually)</option>
            <option value="60">Every hour</option>
            <option value="360">Every 6 hours</option>
            <option value="1440">Daily</option>
            <option value="10080">Weekly</option>
          </select>
        </label>
        <label className="field">
          <span>Contract term reading</span>
          <select value={provider} onChange={(e) => setProvider(e.target.value as "stub" | "anthropic")}>
            <option value="stub">Offline reader (nothing leaves JADAssure)</option>
            <option value="anthropic" disabled={!s.ai_external_available}>
              Claude (external AI){s.ai_external_available ? "" : " · not configured on this server"}
            </option>
          </select>
        </label>
        <label className="field">
          <span>Keep uploaded files for (days)</span>
          <input
            inputMode="numeric"
            placeholder="Keep until deleted"
            value={retention}
            onChange={(e) => setRetention(e.target.value.replace(/[^0-9]/g, ""))}
          />
        </label>
      </div>
      {provider === "anthropic" && s.ai_provider !== "anthropic" && (
        <div className="notice">
          Contract text will be sent to an external AI provider to propose terms. Proposals still need a person to confirm
          them, and no money figure ever comes from AI. This change is recorded in the audit history.
        </div>
      )}
      <p className="muted" style={{ margin: 0, fontSize: 12 }}>
        Retention removes uploaded raw files (import CSVs, error reports, contract originals) older than the period. Records,
        findings and their evidence are kept until the organization's data is deleted.
      </p>
      <div className="row">
        <button className="btn primary" disabled={save.isPending} onClick={() => save.mutate()}>
          Save settings
        </button>
        {msg && <span className={msg.ok ? "muted" : "error"}>{msg.text}</span>}
      </div>
    </section>
  );
}

function AuditCard() {
  const [limit, setLimit] = useState(25);
  const events = useQuery({ queryKey: ["audit", limit], queryFn: () => api<AuditEvent[]>(`/audit?limit=${limit}`) });
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<User[]>("/users"), retry: false });
  const verify = useMutation({ mutationFn: () => api<{ ok: boolean; events: number; first_bad_seq: number | null }>("/audit/verify") });
  const names = new Map((users.data ?? []).map((u) => [u.id, u.name]));

  return (
    <section className="card stack" aria-label="Audit history">
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Audit history</h2>
        <div className="row">
          {verify.data &&
            (verify.data.ok ? (
              <span className="badge ok">Chain intact · {verify.data.events} events</span>
            ) : (
              <span className="badge bad">Tampering detected at #{verify.data.first_bad_seq}</span>
            ))}
          <button className="btn" onClick={() => verify.mutate()} disabled={verify.isPending}>
            Verify chain
          </button>
        </div>
      </div>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th className="num">#</th>
              <th>When</th>
              <th>Who</th>
              <th>What</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {(events.data ?? []).map((e) => (
              <tr key={e.seq}>
                <td className="num">{e.seq}</td>
                <td>{new Date(e.occurred_at).toLocaleString()}</td>
                <td>{e.actor_id ? names.get(e.actor_id) ?? e.actor_id.slice(0, 8) : "JADAssure"}</td>
                <td className="mono">{e.action}</td>
                <td className="mono audit-payload">{JSON.stringify(e.payload)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(events.data?.length ?? 0) >= limit && (
        <div>
          <button className="btn small" onClick={() => setLimit(limit + 50)}>
            Show more
          </button>
        </div>
      )}
    </section>
  );
}

function DangerZone() {
  const { logout } = useAuth();
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api<OrgSettings>("/settings") });
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const del = useMutation({
    mutationFn: () => api("/settings/delete-organization-data", { method: "POST", body: JSON.stringify({ confirm_short_code: code }) }),
    onSuccess: () => logout(),
    onError: (e) => setError(e instanceof ApiError ? e.message : "Deletion failed"),
  });
  const shortCode = settings.data?.short_code ?? "";

  return (
    <section className="card stack danger-zone" aria-label="Delete organization data">
      <h2 style={{ margin: 0 }}>Delete all organization data</h2>
      <p style={{ margin: 0 }}>
        Permanently removes every record, finding, correction, document, uploaded file and user of this organization, including
        you. Only a tombstone entry in the audit history remains. This can't be undone.
      </p>
      <div className="row">
        <input
          aria-label="Type the organization code to confirm"
          placeholder={`Type ${shortCode} to confirm`}
          value={code}
          onChange={(e) => setCode(e.target.value)}
        />
        <button className="btn danger" disabled={del.isPending || code.trim().toUpperCase() !== shortCode} onClick={() => del.mutate()}>
          Delete everything
        </button>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}
