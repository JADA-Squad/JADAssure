import { api } from "../../api/client";

export interface Action {
  id: string;
  tool: string;
  summary: string;
  status: "proposed" | "confirmed" | "cancelled" | "failed";
  result: string | null;
  created_at: string;
  decided_at: string | null;
}

export type Item =
  | { kind: "user"; text: string }
  | { kind: "assistant"; text: string }
  | { kind: "lookup"; text: string }
  | { kind: "action"; action: Action };

export interface Conversation {
  id: string;
  title: string;
  items: Item[];
  notice?: string | null;
}

export interface AssistantStatus {
  available: boolean;
  reason: string | null;
  provider: string | null;
  can_change: string[];
  can_look_up: string[];
}

export const assistantApi = {
  status: () => api<AssistantStatus>("/assistant/status"),
  conversations: () => api<{ id: string; title: string; updated_at: string }[]>("/assistant/conversations"),
  conversation: (id: string) => api<Conversation>(`/assistant/conversations/${id}`),
  create: () => api<Conversation>("/assistant/conversations", { method: "POST" }),
  send: (id: string, text: string) =>
    api<Conversation>(`/assistant/conversations/${id}/messages`, { method: "POST", body: JSON.stringify({ text }) }),
  decide: (id: string, how: "confirm" | "cancel") => api<Action>(`/assistant/actions/${id}/${how}`, { method: "POST" }),
};
