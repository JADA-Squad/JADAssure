import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../../api/client";
import { downloadFile } from "../../components/download";
import { CORRECTION_STATUS_LABELS, formatMoney, ROOT_CAUSE_LABELS } from "../../components/format";
import { useAuth } from "../auth/AuthContext";
import { findingsApi, type FindingDetail } from "./api";

type Decision = "reject" | "send-back" | "approve" | "write-off";

const STATUS_HELP: Record<string, string> = {
  open: "Not yet picked up. Take ownership (or comment) to start the review.",
  in_review: "Under investigation. Propose it for approval with a root cause, or reject it if it isn't leakage.",
  proposed: "Waiting for a finance approver. The proposer can't approve their own proposal.",
  approved: "Approved. A correction has been prepared; it moves to billed when the corrected invoice is imported.",
  billed: "The corrected invoice has been imported. Cash is recovered only when a matching payment is recorded.",
  recovered: "Recovered: a payment against the corrected invoice has been recorded. This finding is final.",
  rejected: "Rejected as not leakage. Final; it never counts in any money figure.",
  closed_no_recovery: "Written off: confirmed leakage that won't be recovered. Final.",
};

/** Workflow actions (FR-27, FR-28): exactly the actions the API says this user may take now. */
export function ActionsPanel({ f }: { f: FindingDetail }) {
  const { session } = useAuth();
  const qc = useQueryClient();
  const can = (a: string) => f.available_actions.includes(a);
  const [error, setError] = useState<string | null>(null);
  const [category, setCategory] = useState(f.root_cause_category ?? "");
  const [cause, setCause] = useState(f.root_cause ?? "");
  const [note, setNote] = useState("");
  const [mode, setMode] = useState<"propose" | Decision | null>(null);
  const owners = useQuery({ queryKey: ["findings", "filters"], queryFn: findingsApi.filters, enabled: can("assign") });

  const done = (updated: FindingDetail) => {
    qc.setQueryData(["findings", "detail", f.id], updated);
    qc.invalidateQueries({ queryKey: ["findings", "list"] });
    setError(null);
    setMode(null);
    setNote("");
  };
  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : "The action failed");
  const assign = useMutation({ mutationFn: (owner: string | null) => findingsApi.assign(f.id, owner), onSuccess: done, onError: fail });
  const propose = useMutation({
    mutationFn: () => findingsApi.propose(f.id, category, cause, note),
    onSuccess: done,
    onError: fail,
  });
  const decide = useMutation({
    mutationFn: (action: Decision) => findingsApi.decide(f.id, action, note),
    onSuccess: done,
    onError: fail,
  });
  const busy = assign.isPending || propose.isPending || decide.isPending;
  const myId = session?.me.user.id;
  const canExport = session?.me.capabilities.includes("export_corrections") ?? false;
  const decisionButtons = (["approve", "send-back", "reject", "write-off"] as Decision[]).filter((d) => can(d.replace("-", "_")));

  return (
    <section className="card stack" aria-label="Actions">
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Next step</h2>
        {f.owner_name && <span className="muted">Owner: {f.owner_name}</span>}
      </div>
      <p className="muted" style={{ margin: 0 }}>
        {STATUS_HELP[f.status]}
      </p>

      {f.root_cause_category && (
        <div>
          <strong>Root cause:</strong> {ROOT_CAUSE_LABELS[f.root_cause_category] ?? f.root_cause_category}. {f.root_cause}
          {f.proposer_name && <span className="muted"> (proposed by {f.proposer_name})</span>}
        </div>
      )}

      {f.status === "proposed" && f.proposer_id === myId && (
        <div className="notice">You proposed this finding, so a different approver must approve it (separation of duties).</div>
      )}

      <div className="row">
        {can("assign") && f.owner_id !== myId && (
          <button className="btn" disabled={busy} onClick={() => assign.mutate(myId ?? null)}>
            Take ownership
          </button>
        )}
        {can("assign") && (owners.data?.owners.length ?? 0) > 0 && (
          <label className="row" style={{ gap: 6 }}>
            <span className="muted">Assign to</span>
            <select
              aria-label="Assign to"
              value={f.owner_id ?? ""}
              disabled={busy}
              onChange={(e) => assign.mutate(e.target.value || null)}
            >
              <option value="">Unassigned</option>
              {owners.data?.owners.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
          </label>
        )}
        {can("propose") && (
          <button className="btn primary" disabled={busy} onClick={() => setMode("propose")}>
            Propose for approval
          </button>
        )}
        {decisionButtons.map((d) => (
          <button
            key={d}
            className={`btn${d === "approve" ? " primary" : ""}`}
            disabled={busy}
            onClick={() => (d === "approve" ? decide.mutate("approve") : setMode(d))}
          >
            {{ approve: "Approve", "send-back": "Send back", reject: "Reject", "write-off": "Write off" }[d]}
          </button>
        ))}
      </div>

      {mode === "propose" && (
        <form
          className="stack"
          style={{ gap: 8 }}
          onSubmit={(e) => {
            e.preventDefault();
            propose.mutate();
          }}
        >
          <label className="field" style={{ margin: 0 }}>
            <span>Root cause category (required)</span>
            <select required aria-label="Root cause category" value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">Choose…</option>
              {Object.entries(ROOT_CAUSE_LABELS).map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="field" style={{ margin: 0 }}>
            <span>What happened (required)</span>
            <textarea required aria-label="What happened" rows={2} maxLength={500} value={cause} onChange={(e) => setCause(e.target.value)} />
          </label>
          <label className="field" style={{ margin: 0 }}>
            <span>Note for the approver (optional)</span>
            <textarea aria-label="Note for the approver" rows={2} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
          <div className="row">
            <button className="btn primary" type="submit" disabled={busy || !category || !cause.trim()}>
              Propose
            </button>
            <button className="btn" type="button" onClick={() => setMode(null)}>
              Cancel
            </button>
          </div>
        </form>
      )}

      {mode && mode !== "propose" && mode !== "approve" && (
        <form
          className="stack"
          style={{ gap: 8 }}
          onSubmit={(e) => {
            e.preventDefault();
            decide.mutate(mode);
          }}
        >
          <label className="field" style={{ margin: 0 }}>
            <span>
              {mode === "reject" ? "Why isn't this leakage?" : mode === "send-back" ? "What needs another look?" : "Why won't this be recovered?"}{" "}
              (required)
            </span>
            <textarea required aria-label="Reason" rows={2} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
          <div className="row">
            <button className="btn primary" type="submit" disabled={busy || !note.trim()}>
              {{ reject: "Reject finding", "send-back": "Send back", "write-off": "Write off" }[mode]}
            </button>
            <button className="btn" type="button" onClick={() => setMode(null)}>
              Cancel
            </button>
          </div>
        </form>
      )}
      {error && <p className="error" role="alert">{error}</p>}

      {f.correction && (
        <div className="correction-box">
          <div className="row spread">
            <div>
              <strong>Prepared correction {f.correction.reference}</strong> ·{" "}
              {f.correction.kind === "credit_reversal" ? "credit reversal" : "supplementary invoice"} ·{" "}
              {formatMoney(f.correction.amount, f.correction.currency)} ·{" "}
              {CORRECTION_STATUS_LABELS[f.correction.status] ?? f.correction.status}
            </div>
            <Link to="/recovery">Recovery tracker →</Link>
          </div>
          <p className="muted" style={{ margin: "6px 0" }}>
            JADAssure never sends invoices. Raise this in your billing system and quote {f.correction.reference} on it.
          </p>
          {canExport && (
            <div className="row">
              {(["csv", "json"] as const).map((fmt) => (
                <button
                  key={fmt}
                  className="btn small"
                  onClick={() =>
                    downloadFile(`/corrections/${f.correction!.id}/export.${fmt}`, `${f.correction!.reference}.${fmt}`, session?.token ?? null).catch(
                      () => setError("Could not download the correction"),
                    )
                  }
                >
                  Export {fmt.toUpperCase()}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="ai-box">
        <span className="badge info">AI-generated · not used in calculations</span>{" "}
        {f.ai_summary ?? <span className="muted">No AI summary. AI assistance is off for this organization.</span>}
      </div>
    </section>
  );
}
