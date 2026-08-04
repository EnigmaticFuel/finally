"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Panel } from "./Panel";
import { quantity } from "@/lib/format";
import type { ChatActions, ChatMessage } from "@/lib/types";

function ActionChips({ actions }: { actions: ChatActions }) {
  const trades = actions.trades ?? [];
  const changes = actions.watchlist_changes ?? [];
  if (trades.length === 0 && changes.length === 0) return null;

  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {trades.map((trade, index) => (
        <span
          key={`trade-${index}`}
          data-testid="chat-action-trade"
          className={`border px-1.5 py-0.5 font-mono text-[10px] tracking-[0.1em] uppercase ${
            trade.side === "buy"
              ? "border-up/50 text-up"
              : "border-down/50 text-down"
          }`}
        >
          {trade.side} {quantity(trade.quantity)} {trade.ticker}
        </span>
      ))}
      {changes.map((change, index) => (
        <span
          key={`watch-${index}`}
          data-testid="chat-action-watchlist"
          className="border border-azure/50 px-1.5 py-0.5 font-mono text-[10px] tracking-[0.1em] text-azure uppercase"
        >
          {change.action === "add" ? "+" : "-"}
          {change.ticker}
        </span>
      ))}
    </div>
  );
}

/** The one panel set in a proportional face: everywhere else is machine
    output, here a person and an assistant are talking. */
export function ChatPanel({
  messages,
  loading,
  collapsed,
  onToggle,
  onSend,
}: {
  messages: ChatMessage[];
  loading: boolean;
  collapsed: boolean;
  onToggle: () => void;
  onSend: (message: string) => void;
}) {
  const [draft, setDraft] = useState("");
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = scroller.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages, loading]);

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={onToggle}
        data-testid="chat-toggle"
        aria-label="Open AI copilot"
        className="flex w-9 shrink-0 cursor-pointer flex-col items-center gap-3 border-l border-line bg-panel py-3 hover:bg-raise"
      >
        <span className="h-3 w-[2px] bg-plum" />
        <span
          className="text-[10px] tracking-[0.18em] text-muted uppercase"
          style={{ writingMode: "vertical-rl" }}
        >
          AI Copilot
        </span>
      </button>
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || loading) return;
    onSend(text);
    setDraft("");
  }

  return (
    <Panel
      label="AI copilot"
      accent="plum"
      actions={
        <button
          type="button"
          onClick={onToggle}
          data-testid="chat-toggle"
          aria-label="Collapse AI copilot"
          className="ml-1 px-1 text-[11px] text-dim hover:text-ink"
        >
          &raquo;
        </button>
      }
      className="w-[360px] shrink-0 border-l border-line"
      bodyClassName="flex flex-col"
    >
      <div
        ref={scroller}
        data-testid="chat-messages"
        className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3 font-sans"
      >
        {messages.length === 0 && !loading ? (
          <p className="pt-8 text-center font-mono text-[11px] tracking-[0.14em] text-dim">
            ASK ABOUT YOUR PORTFOLIO
          </p>
        ) : null}

        {messages.map((message, index) => (
          <div
            key={`${message.created_at}-${index}`}
            data-testid="chat-message"
            data-role={message.role}
            className={
              message.role === "user"
                ? "ml-6 border border-line bg-raise px-3 py-2 text-[13px] text-ink"
                : "border-l-2 border-plum pl-3 text-[13px] leading-relaxed text-ink"
            }
          >
            <span className="mb-1 block font-mono text-[9px] tracking-[0.18em] text-dim uppercase">
              {message.role === "user" ? "You" : "FinAlly"}
            </span>
            <p className="whitespace-pre-wrap">{message.content}</p>
            {message.actions ? <ActionChips actions={message.actions} /> : null}
          </div>
        ))}

        {loading ? (
          <div
            data-testid="chat-loading"
            className="border-l-2 border-plum pl-3 font-mono text-[11px] tracking-[0.16em] text-muted"
          >
            ANALYZING
            <span className="ml-1 inline-block animate-pulse">...</span>
          </div>
        ) : null}
      </div>

      <form
        onSubmit={submit}
        className="flex shrink-0 items-center gap-1.5 border-t border-line bg-rail p-1.5"
      >
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Ask FinAlly..."
          aria-label="Message FinAlly"
          data-testid="chat-input"
          className="min-w-0 flex-1 bg-void px-2 py-1.5 font-sans text-[13px] text-ink outline-none placeholder:text-dim"
        />
        <button
          type="submit"
          disabled={loading}
          data-testid="chat-send"
          className="bg-plum px-3 py-1.5 text-[10px] tracking-[0.16em] text-ink uppercase hover:brightness-125 disabled:opacity-40"
        >
          Send
        </button>
      </form>
    </Panel>
  );
}
