import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api, ApiError } from "../../api/client";
import { downloadFile } from "../../components/download";
import { CHECK_LABELS, CORRECTION_STATUS_LABELS, FINDING_STATUS_LABELS, formatDate, formatMoney } from "../../components/format";
import { useAuth } from "../auth/AuthContext";

interface CorrectionRow {
  id: string;
  reference: string;
  kind: string;
  status: string;
  amount: string;
  currency: string;
  finding_id: string;
  finding_status: string;
  check_type: string;
  customer_name: string | null;
  invoice_numbers: string[];
  billed: string;
  cash_received: string;
  cash_recovered: string;
  events: { kind: string; amount: string; source_entity: string; occurred_on: string }[];
  created_at: string;
}

interface Tracker {
  is_demo: boolean;
  corrections: CorrectionRow[];
}

const STATUS_TONE: Record<string, string> = { prepared: "info", billed: "busy", partially_paid: "busy", paid: "ok" };

/** Recovery tracker (FR-30, FR-37): prepared correction → corrected invoice → payment → verified cash. */
export function RecoveryPage() {
  const { session } = useAuth();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const tracker = useQuery({ queryKey: ["recovery"], queryFn: () => api<Tracker>("/recovery/corrections") });
  const canExport = session?.me.capabilities.includes("export_corrections") ?? false;
  const simulate = useMutation({
    mutationFn: ({ id, stage }: { id: string; stage: "billing" | "payment" }) =>
      api<Tracker>(`/recovery/corrections/${id}/simulate`, { method: "POST", body: JSON.stringify({ stage }) }),
    onSuccess: (data) => {
      setError(null);
      qc.setQueryData(["recovery"], data);
      qc.invalidateQueries({ queryKey: ["findings"] });
      qc.invalidateQueries({ queryKey: ["outcomes"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Simulation failed"),
  });

  const data = tracker.data;
  return (
    <>
      <div className="page-header">
        <h1>Recovery tracker</h1>
        <p className="muted">
          Approved findings become prepared corrections. A correction counts as billed when an imported invoice carries its
          reference, and as cash recovered only when a payment is allocated to that invoice (capped at the correction).
        </p>
      </div>

      {data?.is_demo && (
        <div className="notice" style={{ marginBottom: 16 }}>
          <span className="badge demo">DEMO</span> This is a demo organization. <strong>Simulate billing</strong> and{" "}
          <strong>Simulate payment</strong> stand in for your billing system by importing the corrected invoice and its
          payment, so you can watch recovery happen. They're not available in real organizations.
        </div>
      )}
      {error && <p className="error" role="alert">{error}</p>}

      <section className="card">
        {tracker.isLoading ? (
          <p className="muted">Loading…</p>
        ) : !data || data.corrections.length === 0 ? (
          <div className="placeholder">
            No corrections yet. They appear here when an approver approves a finding.
          </div>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Reference</th>
                  <th>Finding</th>
                  <th>Customer</th>
                  <th className="num">Correction</th>
                  <th>Status</th>
                  <th>Invoice</th>
                  <th className="num">Billed</th>
                  <th className="num">Payments</th>
                  <th className="num">Cash recovered</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.corrections.map((c) => (
                  <tr key={c.id}>
                    <td className="mono">{c.reference}</td>
                    <td>
                      <Link to={`/findings/${c.finding_id}`}>{CHECK_LABELS[c.check_type] ?? c.check_type}</Link>
                      <div className="muted">{FINDING_STATUS_LABELS[c.finding_status] ?? c.finding_status}</div>
                    </td>
                    <td>{c.customer_name}</td>
                    <td className="num">{formatMoney(c.amount, c.currency)}</td>
                    <td>
                      <span className={`badge ${STATUS_TONE[c.status] ?? "info"}`}>{CORRECTION_STATUS_LABELS[c.status] ?? c.status}</span>
                    </td>
                    <td className="mono">{c.invoice_numbers.join(", ") || <span className="muted">Not yet invoiced</span>}</td>
                    <td className="num">{formatMoney(c.billed, c.currency)}</td>
                    <td className="num">
                      {formatMoney(c.cash_received, c.currency)}
                      {c.events.filter((e) => e.kind === "cash").length > 0 && (
                        <div className="muted">
                          last {formatDate(c.events.filter((e) => e.kind === "cash").slice(-1)[0].occurred_on)}
                        </div>
                      )}
                    </td>
                    <td className="num">
                      <strong>{formatMoney(c.cash_recovered, c.currency)}</strong>
                    </td>
                    <td>
                      <div className="row" style={{ gap: 6, flexWrap: "nowrap" }}>
                        {canExport && (
                          <button
                            className="btn small"
                            onClick={() =>
                              downloadFile(`/corrections/${c.id}/export.csv`, `${c.reference}.csv`, session?.token ?? null).catch(() =>
                                setError("Could not download the correction"),
                              )
                            }
                          >
                            Export
                          </button>
                        )}
                        {data.is_demo && canExport && c.status === "prepared" && c.finding_status !== "closed_no_recovery" && (
                          <button
                            className="btn small"
                            disabled={simulate.isPending}
                            onClick={() => simulate.mutate({ id: c.id, stage: "billing" })}
                          >
                            Simulate billing
                          </button>
                        )}
                        {data.is_demo && canExport && ["billed", "partially_paid"].includes(c.status) && (
                          <button
                            className="btn small"
                            disabled={simulate.isPending}
                            onClick={() => simulate.mutate({ id: c.id, stage: "payment" })}
                          >
                            Simulate payment
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
