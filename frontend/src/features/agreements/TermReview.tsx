import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "../../api/client";
import { formatDate, formatDecimal } from "../../components/format";
import { agreementsApi, type ConfirmEdits, type ReviewTerm } from "./api";

/** One proposed term beside its source passage: confirm (optionally edited) or reject (FR-14). */
export function TermReview({ term, canDecide, knownItems }: { term: ReviewTerm; canDecide: boolean; knownItems: string[] }) {
  const qc = useQueryClient();
  const [value, setValue] = useState(formatDecimal(term.value));
  const [item, setItem] = useState(term.item_code ?? "");
  const [from, setFrom] = useState(term.effective_from);
  const [to, setTo] = useState(term.effective_to ?? "");
  const [reason, setReason] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["terms"] });
    qc.invalidateQueries({ queryKey: ["agreements"] });
  };
  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : "The action failed");
  const confirm = useMutation({
    mutationFn: () => {
      const edits: ConfirmEdits = {};
      if (value !== formatDecimal(term.value)) edits.value = value;
      if (item && item !== (term.item_code ?? "")) edits.item_code = item;
      if (from !== term.effective_from) edits.effective_from = from;
      if (to !== (term.effective_to ?? "")) {
        if (to) edits.effective_to = to;
        else edits.clear_effective_to = true;
      }
      return agreementsApi.confirm(term.id, edits);
    },
    onSuccess: refresh,
    onError: fail,
  });
  const reject = useMutation({ mutationFn: () => agreementsApi.reject(term.id, reason), onSuccess: refresh, onError: fail });
  const busy = confirm.isPending || reject.isPending;
  const unit = term.unit === "pct" ? "%" : term.currency ? `${term.currency}${term.unit ? ` per ${term.unit}` : ""}` : term.unit ?? "";
  const needsItem = (term.term_type === "rate" || term.term_type === "escalation") && !item;

  return (
    <div className={`term-review${term.ambiguous ? " ambiguous" : ""}`}>
      <div className="row spread">
        <div>
          <strong>{term.term_type.replace("_", " ")}</strong> · {term.item_code ?? "agreement-wide / item not identified"} ·{" "}
          {formatDecimal(term.value)} {unit} · from {formatDate(term.effective_from)}
          {term.effective_to ? ` to ${formatDate(term.effective_to)}` : ""}
        </div>
        <span className="muted" style={{ fontSize: 12 }}>
          version {term.version_no} · from {term.document_filename ?? term.origin}
        </span>
      </div>
      {term.ambiguous && (
        <div className="notice" style={{ marginTop: 8 }}>
          <strong>Held for confirmation:</strong> {term.ambiguity_reason}
        </div>
      )}
      <blockquote>{term.source_passage}</blockquote>
      <p className="muted" style={{ fontSize: 12, margin: "4px 0 0" }}>
        Proposed from the document, not yet used by any check. Confirm only what the contract really says.
      </p>

      {canDecide && (
        <div className="stack" style={{ gap: 8, marginTop: 10 }}>
          <div className="row">
            <label className="mini-field">
              <span>Value</span>
              <input aria-label="Value" inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} />
            </label>
            <label className="mini-field">
              <span>Item</span>
              <select aria-label="Item" value={item} onChange={(e) => setItem(e.target.value)}>
                <option value="">{term.term_type === "rate" ? "Choose…" : "Agreement-wide"}</option>
                {[...new Set([...knownItems, ...(term.item_code ? [term.item_code] : [])])].sort().map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <label className="mini-field">
              <span>Effective from</span>
              <input aria-label="Effective from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
            </label>
            <label className="mini-field">
              <span>Effective to</span>
              <input aria-label="Effective to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
            </label>
          </div>
          {!rejecting ? (
            <div className="row">
              <button className="btn primary" disabled={busy || needsItem} onClick={() => confirm.mutate()}>
                Confirm term
              </button>
              <button className="btn" disabled={busy} onClick={() => setRejecting(true)}>
                Reject
              </button>
              {needsItem && <span className="muted">Choose the item this rate applies to.</span>}
            </div>
          ) : (
            <div className="row">
              <input
                aria-label="Why reject this term"
                className="grow"
                placeholder="Why isn't this a term to apply?"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
              <button className="btn primary" disabled={busy || !reason.trim()} onClick={() => reject.mutate()}>
                Reject term
              </button>
              <button className="btn" onClick={() => setRejecting(false)}>
                Cancel
              </button>
            </div>
          )}
          {error && <p className="error" role="alert">{error}</p>}
        </div>
      )}
    </div>
  );
}
