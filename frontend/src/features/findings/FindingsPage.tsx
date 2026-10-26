import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { CHECK_LABELS, FINDING_STATUS_LABELS, formatDate, formatMoney } from "../../components/format";
import { RunChecksButton } from "../../components/RunChecksButton";
import { findingsApi, type QueueFilters } from "./api";

const PAGE_SIZE = 50;
const OPEN_STATUSES = "open,in_review,proposed";
const FILTER_KEYS: (keyof QueueFilters)[] = ["min_value", "customer_id", "check_type", "confidence", "status", "owner", "age"];

/** Findings queue (FR-25): prioritised by value × confidence, seven filters. Filters live in the URL. */
export function FindingsPage() {
  const [params, setParams] = useSearchParams();
  const filters: QueueFilters = Object.fromEntries(
    FILTER_KEYS.map((k) => [k, params.get(k) ?? (k === "status" ? OPEN_STATUSES : "")]),
  );
  const page = Number(params.get("page") ?? "0");

  const options = useQuery({ queryKey: ["findings", "filters"], queryFn: findingsApi.filters });
  const list = useQuery({
    queryKey: ["findings", "list", filters, page],
    queryFn: () => findingsApi.list(filters, PAGE_SIZE, page * PAGE_SIZE),
    placeholderData: keepPreviousData,
  });

  function set(key: keyof QueueFilters, value: string) {
    const next = new URLSearchParams(params);
    if (key === "status" ? value === OPEN_STATUSES : !value) next.delete(key);
    else next.set(key, value);
    next.delete("page");
    setParams(next, { replace: true });
  }

  const data = list.data;
  const opts = options.data;
  const totals = data ? Object.entries(data.value_by_currency) : [];

  return (
    <>
      <div className="page-header row spread">
        <div>
          <h1>Findings</h1>
          <p className="muted">
            Potential revenue leakage, highest priority first (value × confidence). Values are estimates until approved.
          </p>
        </div>
        <RunChecksButton />
      </div>

      <section className="card stack">
        <div className="filters" role="search" aria-label="Filter findings">
          <label>
            <span>Min value</span>
            <input
              inputMode="decimal"
              placeholder="0"
              value={filters.min_value}
              onChange={(e) => set("min_value", e.target.value.replace(/[^0-9.]/g, ""))}
            />
          </label>
          <label>
            <span>Customer</span>
            <select value={filters.customer_id} onChange={(e) => set("customer_id", e.target.value)}>
              <option value="">All customers</option>
              {opts?.customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Type</span>
            <select value={filters.check_type} onChange={(e) => set("check_type", e.target.value)}>
              <option value="">All types</option>
              {Object.entries(CHECK_LABELS).map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Confidence</span>
            <select value={filters.confidence} onChange={(e) => set("confidence", e.target.value)}>
              <option value="">Any</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </label>
          <label>
            <span>Age</span>
            <select value={filters.age} onChange={(e) => set("age", e.target.value)}>
              <option value="">Any age</option>
              <option value="7">Last 7 days</option>
              <option value="30">Last 30 days</option>
              <option value="older30">Older than 30 days</option>
            </select>
          </label>
          <label>
            <span>Owner</span>
            <select value={filters.owner} onChange={(e) => set("owner", e.target.value)}>
              <option value="">Anyone</option>
              <option value="unassigned">Unassigned</option>
              {opts?.owners.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Status</span>
            <select value={filters.status} onChange={(e) => set("status", e.target.value)}>
              <option value={OPEN_STATUSES}>Open work</option>
              <option value="">All statuses</option>
              {Object.entries(FINDING_STATUS_LABELS).map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="row spread">
          <span className="muted">
            {data ? `${data.total} finding${data.total === 1 ? "" : "s"}` : "Loading…"}
            {totals.length > 0 && <> · potential value {totals.map(([c, v]) => formatMoney(v, c)).join(" + ")}</>}
          </span>
        </div>

        {data && data.items.length === 0 ? (
          <div className="placeholder">No findings match these filters. Run the checks after importing data.</div>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th className="num">Value</th>
                  <th>Type</th>
                  <th>Customer</th>
                  <th>Item · period</th>
                  <th>Confidence</th>
                  <th>Status</th>
                  <th>Owner</th>
                  <th className="num">Age</th>
                </tr>
              </thead>
              <tbody>
                {data?.items.map((f) => (
                  <tr key={f.id}>
                    <td className="num">
                      <Link to={`/findings/${f.id}`} className="strong-link">
                        {formatMoney(f.value, f.currency)}
                      </Link>
                    </td>
                    <td>
                      <Link to={`/findings/${f.id}`}>{CHECK_LABELS[f.check_type] ?? f.check_type}</Link>
                      <div className="muted clamp">{f.reason}</div>
                    </td>
                    <td>
                      {f.customer_name}
                      <div className="muted">{f.agreement_title}</div>
                    </td>
                    <td>
                      {f.item_code ?? "—"}
                      <div className="muted">{periodText(f.period_start, f.period_end)}</div>
                    </td>
                    <td>
                      <span className={`badge conf-${f.confidence}`}>{f.confidence}</span>
                    </td>
                    <td>{FINDING_STATUS_LABELS[f.status] ?? f.status}</td>
                    <td>{f.owner_name ?? <span className="muted">Unassigned</span>}</td>
                    <td className="num">{f.age_days}d</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {data && data.total > PAGE_SIZE && (
          <div className="row">
            <button className="btn small" disabled={page === 0} onClick={() => setPage(page - 1)}>
              Previous
            </button>
            <span className="muted">
              Page {page + 1} of {Math.ceil(data.total / PAGE_SIZE)}
            </span>
            <button className="btn small" disabled={(page + 1) * PAGE_SIZE >= data.total} onClick={() => setPage(page + 1)}>
              Next
            </button>
          </div>
        )}
      </section>
    </>
  );

  function setPage(n: number) {
    const next = new URLSearchParams(params);
    if (n) next.set("page", String(n));
    else next.delete("page");
    setParams(next);
  }
}

function periodText(start: string | null, end: string | null): string {
  if (!start) return "";
  return start === end || !end ? formatDate(start) : `${formatDate(start)} – ${formatDate(end)}`;
}
