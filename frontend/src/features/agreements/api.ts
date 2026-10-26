import { api } from "../../api/client";

export interface Term {
  id: string;
  source_record_id: string | null;
  item_code: string | null;
  term_type: string;
  value: string;
  unit: string | null;
  currency: string | null;
  effective_from: string;
  effective_to: string | null;
  approval_ref: string | null;
  params: Record<string, unknown>;
  status: "proposed" | "confirmed" | "rejected";
  ambiguous: boolean;
  ambiguity_reason: string | null;
  source_passage: string | null;
  origin: string;
  confirmed_at: string | null;
}

export interface ReviewTerm extends Term {
  agreement_id: string;
  agreement_title: string;
  customer_name: string;
  version_no: number;
  document_id: string | null;
  document_filename: string | null;
}

export interface AgreementSummary {
  id: string;
  source_record_id: string | null;
  title: string;
  customer_id: string;
  customer_name: string;
  start_date: string;
  end_date: string | null;
  billing_frequency: string;
  currency: string;
  version_count: number;
  term_counts: Record<string, number>;
}

export interface AgreementDetail extends AgreementSummary {
  versions: { id: string; version_no: number; effective_from: string; effective_to: string | null; reason: string | null; terms: Term[] }[];
}

export interface Doc {
  id: string;
  filename: string;
  media_type: string;
  size_bytes: number;
  extraction_status: "queued" | "running" | "succeeded" | "failed";
  extraction_error: string | null;
  extraction_stats: { provider?: string; external?: boolean; proposed?: number; ambiguous?: number; discarded?: number; discard_reasons?: string[] };
  created_at: string;
}

export interface RuleRow {
  check_type: string;
  active_version: { id: string; version_no: number; params: Record<string, unknown>; created_at: string };
  history: { version_no: number; created_at: string }[];
}

export interface ConfirmEdits {
  value?: string;
  item_code?: string;
  unit?: string;
  effective_from?: string;
  effective_to?: string;
  clear_effective_to?: boolean;
  note?: string;
}

export const agreementsApi = {
  list: () => api<AgreementSummary[]>("/agreements"),
  get: (id: string) => api<AgreementDetail>(`/agreements/${id}`),
  documents: (id: string) => api<Doc[]>(`/agreements/${id}/documents`),
  upload: (id: string, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return api<Doc>(`/agreements/${id}/documents`, { method: "POST", body });
  },
  extractAgain: (docId: string) => api<Doc>(`/documents/${docId}/extract`, { method: "POST" }),
  proposed: () => api<ReviewTerm[]>("/terms?status=proposed"),
  confirm: (termId: string, edits: ConfirmEdits) =>
    api<ReviewTerm>(`/terms/${termId}/confirm`, { method: "POST", body: JSON.stringify(edits) }),
  reject: (termId: string, reason: string) =>
    api<ReviewTerm>(`/terms/${termId}/reject`, { method: "POST", body: JSON.stringify({ reason }) }),
  rules: () => api<RuleRow[]>("/rules"),
};
