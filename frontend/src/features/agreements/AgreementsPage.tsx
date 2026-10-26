import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";

import { ApiError } from "../../api/client";
import { downloadFile } from "../../components/download";
import { CHECK_LABELS, formatDate, formatDecimal } from "../../components/format";
import { StatusBadge } from "../../components/StatusBadge";
import { useAuth } from "../auth/AuthContext";
import { agreementsApi, type AgreementDetail, type Doc } from "./api";
import { TermReview } from "./TermReview";

/** Rules & agreements (FR-36): agreements, versions and terms, contract documents, term review, rule versions. */
export function AgreementsPage() {
  const list = useQuery({ queryKey: ["agreements", "list"], queryFn: agreementsApi.list });
  const proposed = useQuery({ queryKey: ["terms", "proposed"], queryFn: agreementsApi.proposed });
  const [selected, setSelected] = useState<string | null>(null);
  const agreements = list.data ?? [];
  const current = agreements.find((a) => a.id === selected) ?? agreements[0];
  const pendingBy = (id: string) => (proposed.data ?? []).filter((t) => t.agreement_id === id).length;

  return (
    <>
      <div className="page-header">
        <h1>Rules &amp; agreements</h1>
        <p className="muted">
          Only confirmed terms are used by the checks. Terms read from uploaded contracts are proposals until someone
          confirms them beside the passage they came from.
        </p>
      </div>
      <div className="split">
        <aside className="card stack" aria-label="Agreements">
          <h2 style={{ margin: 0 }}>Agreements</h2>
          {list.isLoading && <p className="muted">Loading…</p>}
          {!list.isLoading && agreements.length === 0 && <p className="muted">No agreements yet. Import them in Data setup.</p>}
          <div>
            {agreements.map((a) => (
              <button key={a.id} className={`list-item${a.id === current?.id ? " active" : ""}`} onClick={() => setSelected(a.id)}>
                <div>
                  {a.title} {pendingBy(a.id) > 0 && <span className="badge busy">{pendingBy(a.id)} to review</span>}
                </div>
                <div className="sub">
                  {a.customer_name} · {a.billing_frequency.replace("_", " ")} · {a.currency}
                </div>
              </button>
            ))}
          </div>
        </aside>
        <div className="stack" style={{ minWidth: 0 }}>
          {current && <AgreementDetailView key={current.id} id={current.id} />}
          <RulesCard />
        </div>
      </div>
    </>
  );
}

function AgreementDetailView({ id }: { id: string }) {
  const { session } = useAuth();
  const canManage = session?.me.capabilities.includes("manage_contracts") ?? false;
  const detail = useQuery({ queryKey: ["agreements", "detail", id], queryFn: () => agreementsApi.get(id) });
  const proposed = useQuery({ queryKey: ["terms", "proposed"], queryFn: agreementsApi.proposed });
  const a = detail.data;
  if (!a) return <p className="muted">Loading…</p>;
  const mine = (proposed.data ?? []).filter((t) => t.agreement_id === id);
  const knownItems = [...new Set(a.versions.flatMap((v) => v.terms.map((t) => t.item_code)).filter((c): c is string => !!c))].sort();

  return (
    <>
      <section className="card">
        <h2 style={{ marginBottom: 2 }}>{a.title}</h2>
        <div className="muted">
          {a.customer_name} · {a.source_record_id} · {formatDate(a.start_date)} → {a.end_date ? formatDate(a.end_date) : "open-ended"} · billed{" "}
          {a.billing_frequency.replace("_", " ")} in {a.currency}
        </div>
      </section>

      <Documents agreementId={id} canManage={canManage} token={session?.token ?? null} />

      {mine.length > 0 && (
        <section className="card stack" aria-label="Proposed terms">
          <h2 style={{ margin: 0 }}>Proposed terms to review ({mine.length})</h2>
          {mine.map((t) => (
            <TermReview key={t.id} term={t} canDecide={canManage} knownItems={knownItems} />
          ))}
        </section>
      )}

      <VersionsCard a={a} />
    </>
  );
}

function Documents({ agreementId, canManage, token }: { agreementId: string; canManage: boolean; token: string | null }) {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const docs = useQuery({
    queryKey: ["agreements", "docs", agreementId],
    queryFn: () => agreementsApi.documents(agreementId),
    refetchInterval: (q) => (q.state.data?.some((d) => ["queued", "running"].includes(d.extraction_status)) ? 1500 : false),
  });
  const done = () => {
    setError(null);
    if (fileRef.current) fileRef.current.value = "";
    qc.invalidateQueries({ queryKey: ["agreements"] });
    window.setTimeout(() => qc.invalidateQueries({ queryKey: ["terms"] }), 2500);
  };
  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : "Upload failed");
  const upload = useMutation({ mutationFn: (f: File) => agreementsApi.upload(agreementId, f), onSuccess: done, onError: fail });
  const again = useMutation({ mutationFn: (docId: string) => agreementsApi.extractAgain(docId), onSuccess: done, onError: fail });

  function submit(e: FormEvent) {
    e.preventDefault();
    const f = fileRef.current?.files?.[0];
    if (f) upload.mutate(f);
  }

  return (
    <section className="card stack" aria-label="Contract documents">
      <h2 style={{ margin: 0 }}>Contract documents</h2>
      {canManage && (
        <form className="row" onSubmit={submit}>
          <input ref={fileRef} type="file" accept=".pdf,.docx,.txt" aria-label="Contract file" required />
          <button className="btn primary" type="submit" disabled={upload.isPending}>
            {upload.isPending ? "Uploading…" : "Upload & read terms"}
          </button>
          <span className="muted">PDF (with text), DOCX or TXT, up to 10 MB. Terms found are proposals only.</span>
        </form>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {(docs.data ?? []).length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>No documents uploaded for this agreement.</p>
      ) : (
        <table className="data">
          <thead>
            <tr>
              <th>Document</th>
              <th>Uploaded</th>
              <th>Reading</th>
              <th>Result</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {docs.data!.map((d: Doc) => (
              <tr key={d.id}>
                <td className="mono">{d.filename}</td>
                <td>{new Date(d.created_at).toLocaleString()}</td>
                <td>
                  <StatusBadge status={d.extraction_status} />
                  {d.extraction_error && <div className="error">{d.extraction_error}</div>}
                </td>
                <td className="muted">
                  {d.extraction_status === "succeeded" &&
                    `${d.extraction_stats.proposed ?? 0} proposed (${d.extraction_stats.ambiguous ?? 0} held as ambiguous), ${d.extraction_stats.discarded ?? 0} discarded · ${
                      d.extraction_stats.external ? "external AI" : "read offline"
                    }`}
                </td>
                <td>
                  <div className="row" style={{ gap: 6, flexWrap: "nowrap" }}>
                    <button
                      className="btn small"
                      onClick={() => downloadFile(`/documents/${d.id}/original`, d.filename, token).catch(() => setError("The original is no longer stored"))}
                    >
                      Original
                    </button>
                    {canManage && ["succeeded", "failed"].includes(d.extraction_status) && (
                      <button className="btn small" disabled={again.isPending} onClick={() => again.mutate(d.id)}>
                        Read again
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function VersionsCard({ a }: { a: AgreementDetail }) {
  return (
    <section className="card stack" aria-label="Versions and terms">
      <h2 style={{ margin: 0 }}>Versions &amp; terms</h2>
      {a.versions.map((v) => (
        <div key={v.id}>
          <h3>
            Version {v.version_no} · {formatDate(v.effective_from)} → {v.effective_to ? formatDate(v.effective_to) : "open-ended"}
            {v.reason && <span className="muted"> · {v.reason}</span>}
          </h3>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Term</th>
                  <th>Item</th>
                  <th className="num">Value</th>
                  <th>Effective</th>
                  <th>Status</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {v.terms.map((t) => (
                  <tr key={t.id}>
                    <td>{t.term_type.replace("_", " ")}</td>
                    <td>{t.item_code ?? <span className="muted">agreement-wide</span>}</td>
                    <td className="num">
                      {formatDecimal(t.value)} {t.unit === "pct" ? "%" : t.currency ?? ""}
                      {t.unit && t.unit !== "pct" ? ` / ${t.unit}` : ""}
                    </td>
                    <td>
                      {formatDate(t.effective_from)} → {t.effective_to ? formatDate(t.effective_to) : "open"}
                    </td>
                    <td>
                      <span className={`badge ${t.status === "confirmed" ? "ok" : t.status === "rejected" ? "bad" : "busy"}`}>{t.status}</span>
                    </td>
                    <td className="muted">
                      {t.origin === "import" ? `import ${t.source_record_id ?? ""}` : t.origin}
                      {t.approval_ref ? ` · ${t.approval_ref}` : ""}
                    </td>
                  </tr>
                ))}
                {v.terms.length === 0 && (
                  <tr>
                    <td colSpan={6} className="muted">
                      No terms in this version.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </section>
  );
}

function RulesCard() {
  const rules = useQuery({ queryKey: ["rules"], queryFn: agreementsApi.rules });
  if (!rules.data) return null;
  return (
    <section className="card" aria-label="Rule configuration">
      <h2>Rule configuration</h2>
      <table className="data">
        <thead>
          <tr>
            <th>Check</th>
            <th>Version</th>
            <th>Parameters</th>
          </tr>
        </thead>
        <tbody>
          {rules.data.map((r) => (
            <tr key={r.check_type}>
              <td>{CHECK_LABELS[r.check_type] ?? r.check_type}</td>
              <td>
                v{r.active_version.version_no}
                <div className="muted">{r.history.length} version{r.history.length === 1 ? "" : "s"}</div>
              </td>
              <td className="mono">
                {Object.entries(r.active_version.params)
                  .map(([k, v]) => `${k.replace(/_/g, " ")}: ${v ?? "—"}`)
                  .join(" · ")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted" style={{ marginBottom: 0, fontSize: 12 }}>
        Every finding records the rule version it was calculated with. Changing parameters creates a new version.
      </p>
    </section>
  );
}
