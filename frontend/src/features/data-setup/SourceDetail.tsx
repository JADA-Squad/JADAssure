import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";

import { ApiError } from "../../api/client";
import { downloadFile } from "../../components/download";
import { StatusBadge } from "../../components/StatusBadge";
import { useAuth } from "../auth/AuthContext";
import { dataSetupApi, isBusy, type DataSource, type ImportBatch, type RecordType } from "./api";
import { ImportReview } from "./ImportReview";

interface Props {
  source: DataSource;
  recordTypes: RecordType[];
}

export function SourceDetail({ source, recordTypes }: Props) {
  const qc = useQueryClient();
  const { session } = useAuth();
  const token = session?.token ?? null;
  const [recordType, setRecordType] = useState(recordTypes[0]?.record_type ?? "customer");
  const [reviewId, setReviewId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const syncPending = useRef(false);

  const imports = useQuery({
    queryKey: ["imports", source.id],
    queryFn: () => dataSetupApi.imports(source.id),
    refetchInterval: (q) => (q.state.data?.some((b) => isBusy(b.status)) || syncPending.current ? 1500 : false),
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ["imports", source.id] });

  const upload = useMutation({
    mutationFn: (file: File) => dataSetupApi.upload(source.id, recordType, file),
    onSuccess: (batch) => {
      setError(null);
      setReviewId(batch.id);
      if (fileRef.current) fileRef.current.value = "";
      refresh();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Upload failed"),
  });
  const sync = useMutation({
    mutationFn: () => dataSetupApi.sync(source.id, "baseline"),
    onSuccess: () => {
      setError(null);
      setNotice("Sync queued. Imports appear below as the worker processes them.");
      syncPending.current = true;
      window.setTimeout(() => (syncPending.current = false), 15000);
      refresh();
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Sync failed"),
  });
  const retry = useMutation({
    mutationFn: (jobId: string) => dataSetupApi.retryJob(jobId),
    onSuccess: refresh,
    onError: (e) => setError(e instanceof ApiError ? e.message : "Retry failed"),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (file) upload.mutate(file);
  }

  const batches = imports.data ?? [];
  const review = batches.find((b) => b.id === reviewId);
  const typeLabel = (t: string) => recordTypes.find((r) => r.record_type === t)?.label ?? t;

  return (
    <div className="stack">
      <section className="card stack">
        <div className="row spread">
          <div>
            <h2 style={{ marginBottom: 2 }}>
              {source.name} {source.is_demo && <span className="badge demo">DEMO</span>}
            </h2>
            <div className="muted">
              {source.kind === "connector"
                ? `Connector: ${source.connector_key}${source.config.dataset ? ` · dataset ${String(source.config.dataset)}` : ""}`
                : "CSV uploads"}
            </div>
          </div>
          {source.kind === "connector" && (
            <button className="btn" onClick={() => sync.mutate()} disabled={sync.isPending}>
              {sync.isPending ? "Queuing…" : "Sync now"}
            </button>
          )}
        </div>
        {source.is_demo && (
          <div className="notice">Demonstration connector: synthetic data, not a live customer integration.</div>
        )}

        <form className="row" onSubmit={submit} aria-label="Upload a CSV file">
          <label className="field" style={{ margin: 0 }}>
            <span className="muted">Record type</span>
            <select value={recordType} onChange={(e) => setRecordType(e.target.value)}>
              {recordTypes.map((r) => (
                <option key={r.record_type} value={r.record_type}>
                  {r.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field" style={{ margin: 0 }}>
            <span className="muted">CSV file</span>
            <input ref={fileRef} type="file" accept=".csv,text/csv" required />
          </label>
          <button className="btn primary" type="submit" disabled={upload.isPending} style={{ alignSelf: "flex-end" }}>
            {upload.isPending ? "Checking…" : "Upload & check"}
          </button>
          <button
            type="button"
            className="btn link"
            style={{ alignSelf: "flex-end", marginBottom: 8 }}
            onClick={() =>
              downloadFile(`/ingestion/templates/${recordType}.csv`, `jadassure-${recordType}-template.csv`, token).catch(() =>
                setError("Could not download the template"),
              )
            }
          >
            Download template
          </button>
        </form>
        {error && <p className="error" role="alert">{error}</p>}
        {notice && !error && <p className="muted">{notice}</p>}
      </section>

      {review && (
        <ImportReview
          batch={review}
          recordType={recordTypes.find((r) => r.record_type === review.record_type)}
          onClose={() => setReviewId(null)}
        />
      )}

      <section className="card">
        <h2>Import history</h2>
        {batches.length === 0 ? (
          <p className="muted">No imports yet for this source.</p>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Record type</th>
                  <th>File</th>
                  <th>Status</th>
                  <th className="num">Inserted</th>
                  <th className="num">Updated</th>
                  <th className="num">Unchanged</th>
                  <th className="num">Rejected</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {batches.map((b) => (
                  <HistoryRow
                    key={b.id}
                    batch={b}
                    label={typeLabel(b.record_type)}
                    selected={b.id === reviewId}
                    onReview={() => setReviewId(b.id)}
                    onRetry={() => b.job_id && retry.mutate(b.job_id)}
                    onErrors={() =>
                      downloadFile(`/imports/${b.id}/errors.csv`, `import-${b.record_type}-errors.csv`, token).catch(() =>
                        setError("Could not download the error report"),
                      )
                    }
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

interface RowProps {
  batch: ImportBatch;
  label: string;
  selected: boolean;
  onReview: () => void;
  onRetry: () => void;
  onErrors: () => void;
}

function HistoryRow({ batch: b, label, selected, onReview, onRetry, onErrors }: RowProps) {
  const done = b.status === "succeeded";
  return (
    <tr className={selected ? "selected" : undefined}>
      <td>{new Date(b.created_at).toLocaleString()}</td>
      <td>{label}</td>
      <td className="mono">{b.filename}</td>
      <td>
        <StatusBadge status={b.status} />
        {b.error && <div className="error">{b.error}</div>}
      </td>
      <td className="num">{done ? b.counts.inserted ?? 0 : "—"}</td>
      <td className="num">{done ? b.counts.updated ?? 0 : "—"}</td>
      <td className="num">{done ? b.counts.unchanged ?? 0 : "—"}</td>
      <td className="num">{done ? b.counts.rejected ?? 0 : "—"}</td>
      <td>
        <div className="row" style={{ gap: 8, flexWrap: "nowrap" }}>
          {b.status === "profiled" && (
            <button className="btn small primary" onClick={onReview}>
              Review
            </button>
          )}
          {b.status !== "profiled" && (
            <button className="btn small" onClick={onReview}>
              Details
            </button>
          )}
          {b.has_error_report && (
            <button className="btn small" onClick={onErrors}>
              Errors CSV
            </button>
          )}
          {b.status === "failed" && b.job_id && (
            <button className="btn small" onClick={onRetry}>
              Retry
            </button>
          )}
        </div>
      </td>
    </tr>
  );
}
