import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { ApiError } from "../../api/client";
import { RunChecksButton } from "../../components/RunChecksButton";
import { StatusBadge } from "../../components/StatusBadge";
import { dataSetupApi } from "./api";
import { SourceDetail } from "./SourceDetail";

/** Data setup (FR-35): sources, uploads, mapping, profiling, history, failures and retry. */
export function DataSetupPage() {
  const qc = useQueryClient();
  const sources = useQuery({ queryKey: ["sources"], queryFn: dataSetupApi.sources });
  const recordTypes = useQuery({ queryKey: ["record-types"], queryFn: dataSetupApi.recordTypes, staleTime: Infinity });
  const [selected, setSelected] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => dataSetupApi.createSource(name.trim()),
    onSuccess: (s) => {
      setName("");
      setError(null);
      setSelected(s.id);
      qc.invalidateQueries({ queryKey: ["sources"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Could not create the source"),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (name.trim()) create.mutate();
  }

  const list = sources.data ?? [];
  const current = list.find((s) => s.id === selected) ?? list[0];

  return (
    <>
      <div className="page-header row spread">
        <div>
          <h1>Data setup</h1>
          <p className="muted">Connect sources, import and map records, and check data quality before it reaches the checks.</p>
        </div>
        <RunChecksButton />
      </div>

      <div className="split">
        <aside className="card stack" aria-label="Data sources">
          <h2 style={{ margin: 0 }}>Sources</h2>
          {sources.isLoading && <p className="muted">Loading…</p>}
          <div>
            {list.map((s) => (
              <button
                key={s.id}
                className={`list-item${s.id === current?.id ? " active" : ""}`}
                onClick={() => setSelected(s.id)}
              >
                <div>
                  {s.name} {s.is_demo && <span className="badge demo">DEMO</span>}
                </div>
                <div className="sub">{s.kind === "connector" ? "Connector" : "CSV uploads"}</div>
              </button>
            ))}
          </div>
          <form className="inline-form" onSubmit={submit}>
            <input aria-label="New source name" placeholder="New CSV source name" value={name} onChange={(e) => setName(e.target.value)} />
            <button className="btn small" type="submit" disabled={!name.trim() || create.isPending}>
              Add
            </button>
          </form>
          {error && <p className="error" role="alert">{error}</p>}
        </aside>

        <div className="stack" style={{ minWidth: 0 }}>
          {current && recordTypes.data ? (
            <SourceDetail key={current.id} source={current} recordTypes={recordTypes.data} />
          ) : (
            !sources.isLoading && <div className="placeholder">Add a data source to start importing.</div>
          )}
          <RecentJobs />
        </div>
      </div>
    </>
  );
}

function RecentJobs() {
  const qc = useQueryClient();
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: dataSetupApi.jobs,
    refetchInterval: (q) => (q.state.data?.some((j) => j.status === "queued" || j.status === "running") ? 1500 : 10000),
  });
  const retry = useMutation({
    mutationFn: dataSetupApi.retryJob,
    onSuccess: () => qc.invalidateQueries(),
  });
  const items = jobs.data ?? [];
  if (items.length === 0) return null;
  return (
    <section className="card">
      <h2>Background jobs</h2>
      <table className="data">
        <thead>
          <tr>
            <th>When</th>
            <th>Job</th>
            <th>Status</th>
            <th className="num">Attempts</th>
            <th>Error</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((j) => (
            <tr key={j.id}>
              <td>{new Date(j.created_at).toLocaleString()}</td>
              <td className="mono">{j.kind}</td>
              <td>
                <StatusBadge status={j.status} />
              </td>
              <td className="num">{j.attempts}</td>
              <td className="error">{j.last_error}</td>
              <td>
                {j.status === "failed" && (
                  <button className="btn small" onClick={() => retry.mutate(j.id)} disabled={retry.isPending}>
                    Retry
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
