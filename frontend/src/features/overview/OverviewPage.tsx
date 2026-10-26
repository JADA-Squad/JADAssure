import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../../api/client";
import { formatMoney, ROOT_CAUSE_LABELS } from "../../components/format";
import { useAuth } from "../auth/AuthContext";
import { TrendChart, type TrendPoint } from "./TrendChart";

interface CurrencyFigures {
  currency: string;
  potential: string;
  confirmed: string;
  corrected_billing: string;
  cash_recovered: string;
  prevented_recurrence: string;
  closed_without_recovery: string;
}

interface Outcomes {
  currencies: CurrencyFigures[];
  counts: { open: number; awaiting_approval: number; in_recovery: number; recovered: number; rejected: number; total: number };
  trend: TrendPoint[];
  root_causes: { category: string; currency: string; count: number; value: string }[];
  notes: Record<string, string>;
}

// The six figures are separate measures, never summed into one another (FR-32).
const TILES: { key: keyof Omit<CurrencyFigures, "currency" | "cash_recovered">; label: string; help: string }[] = [
  { key: "potential", label: "Potential leakage", help: "Open, in review or proposed. Estimates until approved." },
  { key: "confirmed", label: "Confirmed leakage", help: "Approved by a finance approver." },
  { key: "corrected_billing", label: "Corrected billing", help: "Invoiced with a correction reference. Not cash yet." },
  { key: "closed_without_recovery", label: "Closed without recovery", help: "Confirmed, then written off." },
  { key: "prevented_recurrence", label: "Prevented recurrence", help: "Estimate; recurrence tracking arrives in M5." },
];

/** Overview (FR-34): where revenue leaks, what's confirmed, and how much cash actually came back. */
export function OverviewPage() {
  const { session } = useAuth();
  const outcomes = useQuery({ queryKey: ["outcomes"], queryFn: () => api<Outcomes>("/reports/outcomes") });
  const canSeeFindings = session?.me.capabilities.includes("view_findings") ?? false;
  const data = outcomes.data;

  if (outcomes.isLoading) return <p className="muted">Loading…</p>;
  if (!data) return <div className="placeholder">Could not load the overview.</div>;

  return (
    <div className="stack">
      <div className="page-header" style={{ marginBottom: 0 }}>
        <h1>Overview</h1>
        <p className="muted">
          Potential, confirmed, billed and recovered money are reported separately. Cash counts as recovered only when a
          payment against a corrected invoice is recorded.
        </p>
      </div>

      {data.currencies.length === 0 && (
        <div className="placeholder">No findings yet. Import data and run the checks to see outcomes here.</div>
      )}

      {data.currencies.map((c) => (
        <section key={c.currency} className="card stack" aria-label={`Outcomes in ${c.currency}`}>
          <div className="hero">
            <div className="label">Cash recovered · {c.currency}</div>
            <div className="hero-value">{formatMoney(c.cash_recovered, c.currency)}</div>
            <div className="muted">Payments received against corrected invoices, capped at each correction.</div>
          </div>
          <div className="tile-grid">
            {TILES.map((t) => (
              <div key={t.key} className="tile">
                <div className="label">{t.label}</div>
                <div className="value">{formatMoney(c[t.key], c.currency)}</div>
                <div className="help">{t.help}</div>
              </div>
            ))}
          </div>
        </section>
      ))}

      <section className="card">
        <h2>Findings</h2>
        <div className="tile-grid">
          {(
            [
              ["open", "Open work"],
              ["awaiting_approval", "Awaiting approval"],
              ["in_recovery", "In recovery"],
              ["recovered", "Recovered"],
              ["rejected", "Rejected as not leakage"],
            ] as const
          ).map(([k, label]) => (
            <div key={k} className="tile">
              <div className="label">{label}</div>
              <div className="value">{data.counts[k]}</div>
            </div>
          ))}
        </div>
        {canSeeFindings && (
          <p style={{ marginBottom: 0 }}>
            <Link to="/findings">Go to the findings queue →</Link>
          </p>
        )}
      </section>

      {data.currencies.map((c) => (
        <section key={c.currency} className="card">
          <h2>Last 12 months · {c.currency}</h2>
          <TrendChart points={data.trend.filter((p) => p.currency === c.currency)} currency={c.currency} />
        </section>
      ))}

      <section className="card">
        <h2>Top recurring root causes</h2>
        {data.root_causes.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>
            Root causes are recorded when findings are proposed. None yet.
          </p>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Root cause</th>
                <th className="num">Findings</th>
                <th className="num">Value</th>
              </tr>
            </thead>
            <tbody>
              {data.root_causes.map((r) => (
                <tr key={`${r.category}-${r.currency}`}>
                  <td>{ROOT_CAUSE_LABELS[r.category] ?? r.category}</td>
                  <td className="num">{r.count}</td>
                  <td className="num">{formatMoney(r.value, r.currency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
