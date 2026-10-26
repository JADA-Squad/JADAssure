const TONE: Record<string, string> = {
  succeeded: "ok",
  failed: "bad",
  queued: "busy",
  running: "busy",
  profiled: "info",
};

export function StatusBadge({ status }: { status: string }) {
  return <span className={`badge ${TONE[status] ?? "info"}`}>{status}</span>;
}
