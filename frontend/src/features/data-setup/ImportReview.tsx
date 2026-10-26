import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { ApiError } from "../../api/client";
import { dataSetupApi, type ImportBatch, type RecordType } from "./api";

interface Props {
  batch: ImportBatch;
  recordType: RecordType | undefined;
  onClose: () => void;
}

/** Profile + mapping + commit for one uploaded file (FR-05, FR-06, FR-07). */
export function ImportReview({ batch, recordType, onClose }: Props) {
  const qc = useQueryClient();
  const p = batch.profile;
  const [mapping, setMapping] = useState<Record<string, string>>(p.mapping);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setMapping(p.mapping), [p.mapping]);

  const dirty = useMemo(() => JSON.stringify(mapping) !== JSON.stringify(p.mapping), [mapping, p.mapping]);
  const refresh = () => qc.invalidateQueries({ queryKey: ["imports", batch.data_source_id] });

  const save = useMutation({
    mutationFn: () => dataSetupApi.saveMapping(batch.id, mapping),
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Could not save the mapping"),
  });
  const commit = useMutation({
    mutationFn: () => dataSetupApi.commit(batch.id),
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Could not commit the import"),
  });

  const suggest = useMutation({
    mutationFn: () => dataSetupApi.suggestions(batch.id),
    onError: (e) => setError(e instanceof ApiError ? e.message : "Could not get suggestions"),
  });
  const fields = recordType?.fields ?? [];
  const usedTargets = new Set(Object.values(mapping).filter(Boolean));
  const issues = p.fields.filter((f) => f.invalid_count > 0 || (f.required && f.mapped_from && f.empty_count > 0));
  const editable = batch.status === "profiled";

  return (
    <section className="card stack" aria-label="Import review">
      <div className="row spread">
        <div>
          <h2 style={{ marginBottom: 2 }}>
            Review import: {recordType?.label ?? batch.record_type}
          </h2>
          <div className="muted">{batch.filename}</div>
        </div>
        <button className="btn small" onClick={onClose}>
          Close
        </button>
      </div>

      <div className="stat-grid">
        <Stat label="Rows in file" value={p.row_count} />
        <Stat label="New ids (before validation)" value={p.new_records} />
        <Stat label="Already imported (unchanged or updated)" value={p.existing_records} />
        <Stat label="Duplicate ids in file" value={p.duplicate_ids_in_file} />
      </div>

      {p.missing_required_fields.length > 0 && (
        <div className="notice error" role="alert">
          Map these required fields before committing: <strong>{p.missing_required_fields.join(", ")}</strong>
        </div>
      )}
      {p.unmatched_references.map((u) => (
        <div className="notice" key={u.field}>
          {u.rows} row(s) refer to {u.distinct} unknown {u.target.replace(/_/g, " ")} id(s) in <strong>{u.field}</strong>
          {" "}(e.g. {u.samples.join(", ")}). Those rows will be rejected unless the {u.target.replace(/_/g, " ")} records are
          imported first.
        </div>
      ))}

      <div>
        <h3>Column mapping</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Column in your file</th>
                <th>JADAssure field</th>
                <th>Example</th>
              </tr>
            </thead>
            <tbody>
              {p.headers.map((h) => (
                <tr key={h}>
                  <td className="mono">{h}</td>
                  <td>
                    <select
                      aria-label={`Field for column ${h}`}
                      value={mapping[h] ?? ""}
                      disabled={!editable}
                      onChange={(e) => setMapping((m) => ({ ...m, [h]: e.target.value }))}
                    >
                      <option value="">— not imported —</option>
                      {fields.map((f) => (
                        <option key={f.name} value={f.name} disabled={usedTargets.has(f.name) && mapping[h] !== f.name}>
                          {f.name}
                          {f.required ? " *" : ""}
                        </option>
                      ))}
                    </select>{" "}
                    {p.suggested_columns.includes(h) && mapping[h] === p.mapping[h] && (
                      <span className="badge suggested" title="Matched automatically from the column name">
                        suggested
                      </span>
                    )}
                  </td>
                  <td className="muted">{firstValue(p, h)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {editable && p.unmapped_columns.length > 0 && (
          <div className="suggest-box">
            <div className="row spread">
              <span>
                {p.unmapped_columns.length} column{p.unmapped_columns.length === 1 ? " isn't" : "s aren't"} mapped yet.
              </span>
              <button className="btn small" disabled={suggest.isPending} onClick={() => suggest.mutate()}>
                {suggest.isPending ? "Thinking…" : "Suggest mappings"}
              </button>
            </div>
            {suggest.data && (
              <>
                <p className="muted" style={{ margin: "6px 0" }}>
                  <span className="badge info">AI suggestion · {suggest.data.external ? "external AI" : "offline"}</span> Nothing is
                  applied until you choose it and save.
                </p>
                {suggest.data.suggestions.length === 0 && <p className="muted">No confident suggestions.</p>}
                {suggest.data.suggestions.map((s) => (
                  <div key={s.column} className="row" style={{ gap: 8 }}>
                    <span className="mono">{s.column}</span> → <strong>{s.field}</strong>
                    <span className="muted">
                      ({Math.round(s.confidence * 100)}% · {s.reason})
                    </span>
                    <button
                      className="btn small"
                      disabled={mapping[s.column] === s.field}
                      onClick={() => setMapping((m) => ({ ...m, [s.column]: s.field }))}
                    >
                      {mapping[s.column] === s.field ? "Applied" : "Apply"}
                    </button>
                  </div>
                ))}
              </>
            )}
          </div>
        )}
        {editable && (
          <div className="row" style={{ marginTop: 8 }}>
            <button className="btn" disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
              {save.isPending ? "Saving…" : "Save mapping & re-check"}
            </button>
            <span className="muted">* required. Saved mappings are reused for this source next time.</span>
          </div>
        )}
      </div>

      {issues.length > 0 && (
        <div>
          <h3>Data quality</h3>
          <table className="data">
            <thead>
              <tr>
                <th>Field</th>
                <th className="num">Invalid</th>
                <th className="num">Empty</th>
                <th>Examples</th>
              </tr>
            </thead>
            <tbody>
              {issues.map((f) => (
                <tr key={f.field}>
                  <td className="mono">{f.field}</td>
                  <td className="num">{f.invalid_count}</td>
                  <td className="num">{f.required ? f.empty_count : "—"}</td>
                  <td>
                    {f.invalid_samples.map((s) => (
                      <div key={s.row}>
                        row {s.row}: <span className="mono">{s.value || "(blank)"}</span> {s.error}
                      </div>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted">Rows with invalid values are rejected on commit and listed in a downloadable error report.</p>
        </div>
      )}

      {error && <p className="error" role="alert">{error}</p>}
      {editable ? (
        <div className="row">
          <button
            className="btn primary"
            disabled={!p.can_commit || dirty || commit.isPending}
            onClick={() => commit.mutate()}
            title={dirty ? "Save the mapping first" : undefined}
          >
            {commit.isPending ? "Committing…" : `Commit ${p.row_count} rows`}
          </button>
          {dirty && <span className="muted">Save the mapping before committing.</span>}
        </div>
      ) : (
        <div className="notice ok">This import is {batch.status}. See the result in the import history.</div>
      )}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="stat">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}

function firstValue(p: ImportBatch["profile"], header: string): string {
  const field = p.mapping[header];
  const value = field ? p.sample_rows[0]?.[field] : undefined;
  return value ?? "";
}
