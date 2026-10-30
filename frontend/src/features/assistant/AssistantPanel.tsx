import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";

import { ApiError } from "../../api/client";
import type { Role } from "../../app/nav";
import { assistantApi, type Action, type Conversation, type Item } from "./api";

const STARTERS: Record<Role, string[]> = {
  analyst: ["What are my highest-value open findings?", "Explain the biggest open finding", "Run the checks now"],
  approver: ["What's waiting for my approval?", "Summarize the recovery tracker"],
  commercial: ["Which contract terms need review?", "Show pricing opportunities"],
  executive: ["How much leakage have we found and recovered?", "What are the top root causes?"],
  admin: ["Which contract terms need review?", "When did the checks last run?"],
};

/** FE-010: the assistant panel. The agent prepares actions; the user confirms each one (GR-17). */
export function AssistantPanel({ role }: { role: Role }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      {!open && (
        <button className="assistant-fab" onClick={() => setOpen(true)} aria-label="Open the assistant">
          Assistant
        </button>
      )}
      {open && <Panel role={role} onClose={() => setOpen(false)} />}
    </>
  );
}

function Panel({ role, onClose }: { role: Role; onClose: () => void }) {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["assistant-status"], queryFn: assistantApi.status });
  const [conv, setConv] = useState<Conversation | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : "Something went wrong");

  // Reopen the most recent conversation, if any.
  useEffect(() => {
    void assistantApi
      .conversations()
      .then((list) => (list[0] ? assistantApi.conversation(list[0].id).then(setConv) : null))
      .catch(fail);
  }, []);
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [conv]);

  const send = useMutation({
    mutationFn: async (message: string) => {
      const target = conv ?? (await assistantApi.create());
      return assistantApi.send(target.id, message);
    },
    onSuccess: (c) => {
      setConv(c);
      setText("");
      setNotice(c.notice ?? null);
      setError(null);
    },
    onError: fail,
  });
  const decide = useMutation({
    mutationFn: ({ id, how }: { id: string; how: "confirm" | "cancel" }) => assistantApi.decide(id, how),
    onSuccess: (a) => {
      setConv((c) => c && { ...c, items: c.items.map((i) => (i.kind === "action" && i.action.id === a.id ? { ...i, action: a } : i)) });
      setError(null);
      if (a.status === "confirmed") qc.invalidateQueries(); // the change shows on every screen
    },
    onError: fail,
  });

  function submit(e?: FormEvent) {
    e?.preventDefault();
    if (text.trim() && !send.isPending) send.mutate(text.trim());
  }

  const items = conv?.items ?? [];
  const available = status.data?.available;
  return (
    <aside className="assistant-panel" aria-label="Assistant">
      <div className="assistant-head">
        <div>
          <strong>Assistant</strong>
          <div className="muted assistant-sub">
            AI{status.data?.provider ? ` (${status.data.provider})` : ""} · prepares actions, you confirm them
          </div>
        </div>
        <div className="row" style={{ gap: 6 }}>
          <button
            className="btn small"
            onClick={() => {
              setConv(null);
              setNotice(null);
              setError(null);
            }}
          >
            New chat
          </button>
          <button className="btn small" onClick={onClose} aria-label="Close the assistant">
            Close
          </button>
        </div>
      </div>

      <div className="assistant-body">
        {status.data && !available && <div className="notice">{status.data.reason}</div>}
        {available && items.length === 0 && (
          <div className="stack" style={{ gap: 8 }}>
            <p className="muted" style={{ margin: 0 }}>
              Ask about your findings, contracts, recovery or figures. When something needs changing, the assistant
              prepares it as a card for you to confirm. It only has the actions your role allows.
            </p>
            {STARTERS[role].map((s) => (
              <button key={s} className="assistant-starter" onClick={() => send.mutate(s)} disabled={send.isPending}>
                {s}
              </button>
            ))}
          </div>
        )}
        {items.map((item, i) => (
          <ItemView
            key={i}
            item={item}
            busy={decide.isPending}
            onDecide={(id, how) => decide.mutate({ id, how })}
          />
        ))}
        {send.isPending && <div className="assistant-thinking muted">Working on it…</div>}
        {notice && <div className="notice">{notice}</div>}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div ref={endRef} />
      </div>

      <form className="assistant-input" onSubmit={submit}>
        <textarea
          aria-label="Message the assistant"
          placeholder={available ? "Ask or tell the assistant…" : "The assistant isn't available"}
          value={text}
          maxLength={4000}
          rows={2}
          disabled={!available || send.isPending}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button className="btn primary" type="submit" disabled={!available || send.isPending || !text.trim()}>
          Send
        </button>
      </form>
    </aside>
  );
}

function ItemView({ item, busy, onDecide }: { item: Item; busy: boolean; onDecide: (id: string, how: "confirm" | "cancel") => void }) {
  if (item.kind === "user") return <div className="assistant-msg user">{item.text}</div>;
  if (item.kind === "assistant") return <div className="assistant-msg bot">{renderText(item.text)}</div>;
  if (item.kind === "lookup") return <div className="assistant-lookup muted">↳ {item.text}</div>;
  return <ActionCard action={item.action} busy={busy} onDecide={onDecide} />;
}

const STATUS_TEXT: Record<Action["status"], string> = {
  proposed: "Waiting for you",
  confirmed: "Done",
  cancelled: "Cancelled",
  failed: "Couldn't be done",
};

function ActionCard({ action, busy, onDecide }: { action: Action; busy: boolean; onDecide: (id: string, how: "confirm" | "cancel") => void }) {
  const money = action.tool === "approve_finding" || action.tool === "write_off_finding";
  return (
    <div className={`assistant-action ${action.status}`}>
      <div className="row spread">
        <span className="badge info">Prepared action</span>
        <span className="assistant-action-status">{STATUS_TEXT[action.status]}</span>
      </div>
      <p style={{ margin: "6px 0" }}>{action.summary}</p>
      {money && action.status === "proposed" && (
        <p className="muted" style={{ margin: "0 0 6px" }}>
          This is a financial decision. Check the finding before confirming.
        </p>
      )}
      {action.status === "proposed" ? (
        <div className="row" style={{ gap: 6 }}>
          <button className="btn small primary" disabled={busy} onClick={() => onDecide(action.id, "confirm")}>
            Confirm
          </button>
          <button className="btn small" disabled={busy} onClick={() => onDecide(action.id, "cancel")}>
            Cancel
          </button>
        </div>
      ) : (
        action.result && <p className="muted" style={{ margin: 0 }}>{action.result}</p>
      )}
    </div>
  );
}

/** Minimal, safe formatting for the assistant's text: paragraphs, bullets, **bold** and | tables |. No HTML. */
function renderText(text: string): ReactNode {
  const blocks: ReactNode[] = [];
  let bullets: string[] = [];
  let rows: string[][] = [];
  const flush = () => {
    if (bullets.length) blocks.push(<ul key={blocks.length}>{bullets.map((b, i) => <li key={i}>{bold(b)}</li>)}</ul>);
    bullets = [];
    if (rows.length) {
      const [head, ...body] = rows;
      blocks.push(
        <div className="table-wrap" key={blocks.length}>
          <table className="data assistant-table">
            <thead>
              <tr>{head.map((c, i) => <th key={i}>{bold(c)}</th>)}</tr>
            </thead>
            <tbody>
              {body.map((r, i) => (
                <tr key={i}>{r.map((c, j) => <td key={j}>{bold(c)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
    }
    rows = [];
  };
  for (const line of text.split("\n")) {
    if (/^\s*\|.*\|\s*$/.test(line)) {
      if (bullets.length) flush();
      const cells = line.trim().slice(1, -1).split("|").map((c) => c.trim());
      if (!cells.every((c) => /^:?-{2,}:?$/.test(c))) rows.push(cells); // skip the |---| separator row
      continue;
    }
    if (!line.trim() && rows.length) continue; // blank lines inside a table
    const m = line.match(/^\s*[-*•]\s+(.*)$/);
    if (m) {
      if (rows.length) flush();
      bullets.push(m[1]);
      continue;
    }
    flush();
    if (line.trim()) blocks.push(<p key={blocks.length}>{bold(line)}</p>);
  }
  flush();
  return blocks;
}

function bold(line: string): ReactNode {
  return line.split(/\*\*(.+?)\*\*/g).map((part, i) => (i % 2 ? <strong key={i}>{part}</strong> : <Fragment key={i}>{part}</Fragment>));
}
