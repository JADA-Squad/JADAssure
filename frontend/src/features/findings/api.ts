import { api } from "../../api/client";

export interface FindingItem {
  id: string;
  check_type: string;
  family: string;
  status: string;
  value: string;
  currency: string;
  confidence: "high" | "medium" | "low";
  priority: string;
  customer_id: string | null;
  customer_name: string | null;
  agreement_title: string | null;
  item_code: string | null;
  period_start: string | null;
  period_end: string | null;
  owner_id: string | null;
  owner_name: string | null;
  reason: string;
  age_days: number;
  created_at: string;
}

export interface FindingPage {
  items: FindingItem[];
  total: number;
  value_by_currency: Record<string, string>;
}

export type EvidenceRecord = Record<string, string | number | null | Record<string, unknown>>;

export interface FindingDetail extends FindingItem {
  also_detected_by: string[];
  recommended_action: string;
  calculation: {
    formula: string;
    inputs: Record<string, string | number | null>;
    components?: Record<string, string>;
    violations?: string[];
    result: string;
  };
  evidence: {
    customer: EvidenceRecord;
    agreement: EvidenceRecord | null;
    terms: EvidenceRecord[];
    delivered: EvidenceRecord[];
    billed: EvidenceRecord[];
    credit?: EvidenceRecord;
  };
  rule_version: { id: string; version_no: number; params: Record<string, unknown> };
  root_cause_category: string | null;
  root_cause: string | null;
  proposer_id: string | null;
  proposer_name: string | null;
  correction: { id: string; reference: string; kind: string; status: string; amount: string; currency: string } | null;
  available_actions: string[];
  recurrence_of: { id: string; check_type: string; status: string; period_start: string | null; root_cause_category: string | null; root_cause: string | null } | null;
  ai_summary: string | null;
  first_detected_at: string;
  last_checked_at: string;
  timeline: { at: string; kind: string; actor_name: string | null; body: string | null; data: Record<string, unknown> }[];
}

export interface FindingFilters {
  customers: { id: string; name: string }[];
  owners: { id: string; name: string }[];
  check_types: string[];
  statuses: string[];
}

export interface QueueFilters {
  min_value?: string;
  customer_id?: string;
  check_type?: string;
  confidence?: string;
  status?: string;
  owner?: string; // owner id or "unassigned"
  age?: string; // "7" | "30" | "older30"
}

export function queueQuery(f: QueueFilters, limit: number, offset: number): string {
  const p = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (f.min_value) p.set("min_value", f.min_value);
  if (f.customer_id) p.set("customer_id", f.customer_id);
  if (f.check_type) p.set("check_type", f.check_type);
  if (f.confidence) p.set("confidence", f.confidence);
  if (f.status) for (const s of f.status.split(",")) p.append("status", s);
  if (f.owner === "unassigned") p.set("unassigned", "true");
  else if (f.owner) p.set("owner_id", f.owner);
  if (f.age === "older30") p.set("min_age_days", "30");
  else if (f.age) p.set("max_age_days", f.age);
  return p.toString();
}

export const findingsApi = {
  list: (f: QueueFilters, limit: number, offset: number) => api<FindingPage>(`/findings?${queueQuery(f, limit, offset)}`),
  filters: () => api<FindingFilters>("/findings/filters"),
  get: (id: string) => api<FindingDetail>(`/findings/${id}`),
  comment: (id: string, body: string) =>
    api<FindingDetail>(`/findings/${id}/comments`, { method: "POST", body: JSON.stringify({ body }) }),
  summarize: (id: string) => api<{ provider: string; ai_summary: string }>(`/findings/${id}/summary`, { method: "POST" }),
  assign: (id: string, owner_id: string | null) =>
    api<FindingDetail>(`/findings/${id}/assign`, { method: "POST", body: JSON.stringify({ owner_id }) }),
  propose: (id: string, root_cause_category: string, root_cause: string, note: string) =>
    api<FindingDetail>(`/findings/${id}/propose`, {
      method: "POST",
      body: JSON.stringify({ root_cause_category, root_cause, note: note || null }),
    }),
  decide: (id: string, action: "reject" | "send-back" | "approve" | "write-off", note: string) =>
    api<FindingDetail>(`/findings/${id}/${action}`, { method: "POST", body: JSON.stringify({ note: note || null }) }),
};
