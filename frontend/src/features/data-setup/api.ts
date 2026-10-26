import { api } from "../../api/client";

export interface DataSource {
  id: string;
  name: string;
  kind: "csv" | "connector";
  connector_key: string | null;
  is_demo: boolean;
  config: Record<string, unknown>;
  mapping: Record<string, Record<string, string>>;
  created_at: string;
}

export interface FieldSpec {
  name: string;
  type: string;
  required: boolean;
  description: string;
  ref: string | null;
  choices: string[];
}

export interface RecordType {
  record_type: string;
  label: string;
  depends_on: string[];
  fields: FieldSpec[];
}

export interface FieldStat {
  field: string;
  required: boolean;
  mapped_from: string | null;
  empty_count: number;
  invalid_count: number;
  invalid_samples: { row: number; value: string; error: string }[];
}

export interface Profile {
  row_count: number;
  headers: string[];
  mapping: Record<string, string>;
  suggested_columns: string[];
  unmapped_columns: string[];
  missing_required_fields: string[];
  fields: FieldStat[];
  unmatched_references: { field: string; target: string; distinct: number; rows: number; samples: string[] }[];
  duplicate_ids_in_file: number;
  existing_records: number;
  new_records: number;
  sample_rows: Record<string, string>[];
  can_commit: boolean;
}

export type ImportStatus = "profiled" | "queued" | "running" | "succeeded" | "failed";

export interface ImportBatch {
  id: string;
  data_source_id: string;
  record_type: string;
  filename: string;
  status: ImportStatus;
  counts: Partial<Record<"inserted" | "updated" | "unchanged" | "rejected", number>>;
  profile: Profile;
  error: string | null;
  job_id: string | null;
  has_error_report: boolean;
  is_demo: boolean;
  created_at: string;
  updated_at: string;
}

export interface Job {
  id: string;
  kind: string;
  status: ImportStatus;
  attempts: number;
  last_error: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface Connector {
  key: string;
  label: string;
  description: string;
  is_demo: boolean;
  options: Record<string, string[]>;
}

export const dataSetupApi = {
  sources: () => api<DataSource[]>("/data-sources"),
  createSource: (name: string) => api<DataSource>("/data-sources", { method: "POST", body: JSON.stringify({ name }) }),
  recordTypes: () => api<RecordType[]>("/ingestion/record-types"),
  connectors: () => api<Connector[]>("/connectors"),
  imports: (sourceId: string) => api<ImportBatch[]>(`/imports?data_source_id=${sourceId}&limit=100`),
  upload: (sourceId: string, recordType: string, file: File) => {
    const body = new FormData();
    body.append("record_type", recordType);
    body.append("file", file);
    return api<ImportBatch>(`/data-sources/${sourceId}/imports`, { method: "POST", body });
  },
  saveMapping: (importId: string, mapping: Record<string, string>) =>
    api<ImportBatch>(`/imports/${importId}/mapping`, { method: "PUT", body: JSON.stringify({ mapping }) }),
  commit: (importId: string) => api<ImportBatch>(`/imports/${importId}/commit`, { method: "POST" }),
  sync: (sourceId: string, stage: string) =>
    api<{ job_id: string; status: string; is_demo: boolean }>(`/data-sources/${sourceId}/sync`, {
      method: "POST",
      body: JSON.stringify({ stage }),
    }),
  jobs: () => api<Job[]>("/jobs?limit=20"),
  retryJob: (jobId: string) => api<Job>(`/jobs/${jobId}/retry`, { method: "POST" }),
};

export const isBusy = (status: string) => status === "queued" || status === "running";
