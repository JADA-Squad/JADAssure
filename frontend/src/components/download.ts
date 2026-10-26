import { ApiError } from "../api/client";

/** Downloads an authenticated API file (templates, error reports) via a temporary object URL. */
export async function downloadFile(path: string, filename: string, token: string | null) {
  const res = await fetch(`/api${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
