import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { api, ApiError } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";
import { formatDateTime } from "./format";

interface CheckRun {
  id: string;
  trigger: string;
  status: "queued" | "running" | "succeeded" | "failed";
  stats: { detected?: number; new?: number; refreshed?: number; frozen?: number };
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

/** "Run checks now" (FR-10) plus the latest run's outcome. Shown to roles with run_checks. */
export function RunChecksButton() {
  const { session } = useAuth();
  const qc = useQueryClient();
  const canRun = session?.me.capabilities.includes("run_checks") ?? false;
  const [error, setError] = useState<string | null>(null);
  const runs = useQuery({
    queryKey: ["check-runs"],
    queryFn: () => api<CheckRun[]>("/check-runs?limit=1"),
    refetchInterval: (q) => (q.state.data?.[0] && ["queued", "running"].includes(q.state.data[0].status) ? 1500 : false),
  });
  const latest = runs.data?.[0];
  const busy = latest ? ["queued", "running"].includes(latest.status) : false;

  // When a run finishes, refresh everything that shows findings.
  const wasBusy = useRef(false);
  useEffect(() => {
    if (wasBusy.current && !busy) qc.invalidateQueries({ queryKey: ["findings"] });
    wasBusy.current = busy;
  }, [busy, qc]);

  const start = useMutation({
    mutationFn: () => api<CheckRun>("/check-runs", { method: "POST" }),
    onSuccess: () => {
      setError(null);
      qc.invalidateQueries({ queryKey: ["check-runs"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Could not start the checks"),
  });

  return (
    <div className="stack" style={{ gap: 4, alignItems: "flex-end" }}>
      {canRun && (
        <button className="btn primary" disabled={busy || start.isPending} onClick={() => start.mutate()}>
          {busy ? "Checks running…" : "Run checks now"}
        </button>
      )}
      {latest && (
        <span className="muted" style={{ fontSize: 12 }}>
          {latest.status === "succeeded" &&
            `Last run ${formatDateTime(latest.finished_at)}: ${latest.stats.detected ?? 0} discrepancies, ${latest.stats.new ?? 0} new`}
          {latest.status === "failed" && <span className="error">Last run failed: {latest.error}</span>}
          {busy && `Run ${latest.status}…`}
        </span>
      )}
      {error && <span className="error">{error}</span>}
    </div>
  );
}
