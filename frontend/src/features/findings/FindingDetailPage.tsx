import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import {
  CHECK_LABELS,
  FINDING_STATUS_LABELS,
  formatDate,
  formatDateTime,
  formatDecimal,
  formatMoney,
} from "../../components/format";
import { useAuth } from "../auth/AuthContext";
import { findingsApi, type EvidenceRecord, type FindingDetail } from "./api";

/** Finding detail (FR-26): side-by-side evidence, calculation, timeline, comments. Workflow actions arrive in M3. */
export function FindingDetailPage() {
  const { id = "" } = useParams();
  const finding = useQuery({ queryKey: ["findings", "detail", id], queryFn: () => findingsApi.get(id) });

  if (finding.isLoading) return <p className="muted">Loading…</p>;
  if (finding.error || !finding.data) {
    return (
      <div className="placeholder" role="alert">
        Finding not found. <Link to="/findings">Back to findings</Link>
      </div>
    );
  }
  const f = finding.data;

  return (
    <div className="stack">
      <div>
        <Link to="/findings">← Findings</Link>
      </div>
      <section className="card stack">
        <div className="row spread" style={{ alignItems: "flex-start" }}>
          <div>
            <h1>{CHECK_LABELS[f.check_type] ?? f.check_type}</h1>
            <div className="muted">
              {f.customer_name}
              {f.agreement_title && ` · ${f.agreement_title}`}
              {f.item_code && ` · ${f.item_code}`}
              {f.period_start && ` · ${formatDate(f.period_start)}${f.period_end && f.period_end !== f.period_start ? ` – ${formatDate(f.period_end)}` : ""}`}
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div className="big-value">{formatMoney(f.value, f.currency)}</div>
            <div className="row" style={{ justifyContent: "flex-end", gap: 6 }}>
              <span className="badge info">{FINDING_STATUS_LABELS[f.status] ?? f.status}</span>
              <span className={`badge conf-${f.confidence}`}>{f.confidence} confidence</span>
            </div>
            <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
              Estimated (potential) value: not confirmed until approved
            </div>
          </div>
        </div>
        <p style={{ margin: 0 }}>{f.reason}</p>
        <div className="notice info-notice">
          <strong>Recommended next action:</strong> {f.recommended_action}
        </div>
        {f.also_detected_by.length > 0 && (
          <p className="muted" style={{ margin: 0 }}>
            Also detected by: {f.also_detected_by.map((c) => CHECK_LABELS[c] ?? c).join(", ")}. Counted once.
          </p>
        )}
      </section>

      <Evidence f={f} />
      <Calculation f={f} />
      <Timeline f={f} />
    </div>
  );
}

function Evidence({ f }: { f: FindingDetail }) {
  const e = f.evidence;
  return (
    <section className="card">
      <h2>Evidence</h2>
      <div className="evidence-grid">
        <div>
          <h3>Agreed</h3>
          {e.agreement && (
            <p className="muted" style={{ marginTop: 0 }}>
              {String(e.agreement.title)} ({String(e.agreement.source_record_id)}) · billed {String(e.agreement.billing_frequency)}
            </p>
          )}
          {e.terms.length === 0 && <p className="muted">No contract term applies; rule defaults were used.</p>}
          {e.terms.map((t) => (
            <div key={String(t.id)} className="evidence-item">
              <div>
                <strong>{String(t.term_type).replace("_", " ")}</strong> {t.item_code ? `· ${t.item_code}` : "· agreement-wide"}
              </div>
              <div>
                {formatDecimal(t.value as string)} {t.unit === "pct" ? "%" : (t.currency as string) ?? ""}{" "}
                {t.unit && t.unit !== "pct" ? `per ${t.unit}` : ""}
              </div>
              <div className="muted">
                {formatDate(t.effective_from as string)} → {t.effective_to ? formatDate(t.effective_to as string) : "open-ended"}
                {t.version_no ? ` · version ${t.version_no}` : ""} · {String(t.source_record_id ?? t.origin)}
                {t.approval_ref ? ` · approval ${t.approval_ref}` : ""}
              </div>
              {t.source_passage && <blockquote>{String(t.source_passage)}</blockquote>}
            </div>
          ))}
        </div>
        <div>
          <h3>Delivered</h3>
          {e.delivered.length === 0 ? (
            <p className="muted">Not applicable to this check.</p>
          ) : (
            <MiniTable
              rows={e.delivered}
              cols={[
                ["source_record_id", "Event"],
                ["service_date", "Date"],
                ["quantity", "Qty"],
              ]}
            />
          )}
        </div>
        <div>
          <h3>Billed</h3>
          {e.credit && (
            <div className="evidence-item">
              <div>
                <strong>Credit {String(e.credit.source_record_id)}</strong> · {formatMoney(e.credit.amount as string, e.credit.currency as string)}
              </div>
              <div className="muted">
                {formatDate(e.credit.credit_date as string)} · reason {e.credit.reason_code ? String(e.credit.reason_code) : "none"} ·
                approval {e.credit.approval_ref ? String(e.credit.approval_ref) : "none"}
                {e.credit.invoice_number ? ` · invoice ${e.credit.invoice_number}` : ""}
              </div>
            </div>
          )}
          {e.billed.length === 0 && !e.credit ? (
            <p className="muted">Nothing was invoiced for this delivery.</p>
          ) : (
            e.billed.length > 0 && (
              <MiniTable
                rows={e.billed}
                cols={[
                  ["invoice_number", "Invoice"],
                  ["quantity", "Qty"],
                  ["unit_price", "Unit price"],
                  ["discount_pct", "Disc %"],
                  ["net_amount", "Net"],
                ]}
              />
            )
          )}
        </div>
      </div>
      <p className="muted" style={{ marginBottom: 0, fontSize: 12 }}>
        Snapshot of source records when the finding was last checked ({formatDateTime(f.last_checked_at)}). Customer
        {" "}{String(f.evidence.customer.name)} ({String(f.evidence.customer.source_record_id)}).
      </p>
    </section>
  );
}

function MiniTable({ rows, cols }: { rows: EvidenceRecord[]; cols: [string, string][] }) {
  return (
    <table className="data">
      <thead>
        <tr>
          {cols.map(([k, label]) => (
            <th key={k}>{label}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={String(r.id)}>
            {cols.map(([k]) => (
              <td key={k} className={k === "source_record_id" || k === "invoice_number" ? "mono" : undefined}>
                {k.endsWith("date") ? formatDate(r[k] as string) : formatDecimal(r[k] as string)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Calculation({ f }: { f: FindingDetail }) {
  const c = f.calculation;
  return (
    <section className="card">
      <h2>Calculation</h2>
      <p className="mono" style={{ marginTop: 0 }}>
        {c.formula}
      </p>
      <table className="data" style={{ maxWidth: 560 }}>
        <tbody>
          {orderedInputs(c.inputs).map(([k, v]) => (
            <tr key={k}>
              <td className="muted">{k.replace(/_/g, " ")}</td>
              <td className="num">{v === null ? "—" : typeof v === "number" ? v : formatDecimal(v)}</td>
            </tr>
          ))}
          {c.components &&
            Object.entries(c.components).map(([k, v]) => (
              <tr key={k}>
                <td className="muted">{k} component</td>
                <td className="num">{formatMoney(v, f.currency)}</td>
              </tr>
            ))}
          <tr>
            <td>
              <strong>Result</strong>
            </td>
            <td className="num">
              <strong>{formatMoney(c.result, f.currency)}</strong>
            </td>
          </tr>
        </tbody>
      </table>
      {c.violations && <p>Policy violations: {c.violations.join("; ")}.</p>}
      <p className="muted" style={{ marginBottom: 0, fontSize: 12 }}>
        Deterministic calculation from confirmed terms using rule version {f.rule_version.version_no}. No AI is involved
        in this value.
      </p>
    </section>
  );
}

// JSONB doesn't keep key order, so present calculation inputs in reading order.
const INPUT_ORDER = [
  "delivered", "billed", "unbilled", "quantity", "service_date", "billed_unit_price", "billed_discount_pct",
  "billed_net_amount", "contracted_base_rate", "contracted_list_price", "list_price", "approved_discount_pct",
  "net_unit_price", "expected_net_unit_price", "expected_net_amount", "amount", "reason_code", "approval_ref",
  "approval_threshold", "max_credit", "policy_source", "billing_due", "grace_days", "as_of",
];

function orderedInputs(inputs: Record<string, string | number | null>) {
  const rank = (k: string) => (INPUT_ORDER.includes(k) ? INPUT_ORDER.indexOf(k) : INPUT_ORDER.length);
  return Object.entries(inputs).sort(([a], [b]) => rank(a) - rank(b));
}

function Timeline({ f }: { f: FindingDetail }) {
  const { session } = useAuth();
  const qc = useQueryClient();
  const canComment = session?.me.capabilities.includes("comment_assign") ?? false;
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const comment = useMutation({
    mutationFn: () => findingsApi.comment(f.id, body),
    onSuccess: (updated) => {
      setBody("");
      setError(null);
      qc.setQueryData(["findings", "detail", f.id], updated);
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Could not add the comment"),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (body.trim()) comment.mutate();
  }

  return (
    <section className="card">
      <h2>Timeline</h2>
      <ol className="timeline">
        {f.timeline.map((t, i) => (
          <li key={i}>
            <span className="muted">{formatDateTime(t.at)}</span> ·{" "}
            <strong>{t.actor_name ?? "JADAssure"}</strong> {t.kind === "comment" ? "commented" : t.kind}
            {t.body && <div className="timeline-body">{t.body}</div>}
          </li>
        ))}
      </ol>
      {canComment && (
        <form onSubmit={submit} className="stack" style={{ gap: 8 }}>
          <textarea
            aria-label="Add a comment"
            rows={3}
            maxLength={4000}
            placeholder="Add a comment for the investigation…"
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          {error && <p className="error">{error}</p>}
          <div>
            <button className="btn" type="submit" disabled={!body.trim() || comment.isPending}>
              {comment.isPending ? "Saving…" : "Add comment"}
            </button>
          </div>
        </form>
      )}
      <p className="muted" style={{ marginBottom: 0, fontSize: 12 }}>
        Propose, reject and approve actions arrive in M3.
      </p>
    </section>
  );
}
