"use client";

import { useEffect, useState, type FormEvent } from "react";
import { money, price, quantity as formatQuantity } from "@/lib/format";
import type { TradeFill } from "@/lib/types";

type Status =
  | { kind: "idle" }
  | { kind: "working" }
  | { kind: "filled"; fill: TradeFill }
  | { kind: "error"; message: string };

/** The command line of the terminal. Market orders, instant fill, and the
    server's fill price reported back rather than the price that was clicked. */
export function TradeBar({
  selected,
  onSubmit,
}: {
  selected: string | null;
  onSubmit: (
    ticker: string,
    quantity: number,
    side: "buy" | "sell",
  ) => Promise<TradeFill>;
}) {
  const [ticker, setTicker] = useState("");
  const [amount, setAmount] = useState("");
  const [status, setStatus] = useState<Status>({ kind: "idle" });

  useEffect(() => {
    if (selected) setTicker(selected);
  }, [selected]);

  async function trade(side: "buy" | "sell") {
    const symbol = ticker.trim().toUpperCase();
    const size = Number(amount);
    if (!symbol || !Number.isFinite(size) || size <= 0) {
      setStatus({ kind: "error", message: "Enter a symbol and a quantity above zero." });
      return;
    }

    setStatus({ kind: "working" });
    try {
      const fill = await onSubmit(symbol, size, side);
      setStatus({ kind: "filled", fill });
      setAmount("");
    } catch (error) {
      setStatus({
        kind: "error",
        message: error instanceof Error ? error.message : "Trade failed.",
      });
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void trade("buy");
  }

  const busy = status.kind === "working";

  return (
    <form
      onSubmit={submit}
      className="flex h-12 shrink-0 items-center gap-3 border-t border-line bg-panel px-4"
    >
      <span className="flex items-center gap-2 text-[10px] tracking-[0.18em] text-muted uppercase">
        <span className="h-3 w-[2px] bg-azure" />
        Order
      </span>

      <input
        value={ticker}
        onChange={(event) => setTicker(event.target.value)}
        placeholder="SYMBOL"
        aria-label="Trade symbol"
        data-testid="trade-ticker"
        className="w-28 border border-line bg-void px-2 py-1.5 text-[12px] tracking-wide text-ink uppercase outline-none placeholder:text-dim placeholder:tracking-[0.14em] focus:border-azure"
      />
      <input
        value={amount}
        onChange={(event) => setAmount(event.target.value)}
        placeholder="QTY"
        aria-label="Trade quantity"
        data-testid="trade-quantity"
        inputMode="decimal"
        className="w-24 border border-line bg-void px-2 py-1.5 text-right text-[12px] text-ink outline-none placeholder:text-dim placeholder:tracking-[0.14em] focus:border-azure"
      />

      <button
        type="button"
        disabled={busy}
        onClick={() => void trade("buy")}
        data-testid="trade-buy"
        className="border border-up bg-up/15 px-6 py-1.5 text-[11px] tracking-[0.18em] text-up uppercase hover:bg-up/25 disabled:opacity-40"
      >
        Buy
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={() => void trade("sell")}
        data-testid="trade-sell"
        className="border border-down bg-down/15 px-6 py-1.5 text-[11px] tracking-[0.18em] text-down uppercase hover:bg-down/25 disabled:opacity-40"
      >
        Sell
      </button>

      <div
        data-testid="trade-status"
        className="min-w-0 flex-1 truncate text-[11px]"
      >
        {status.kind === "working" ? (
          <span className="text-muted">Routing order...</span>
        ) : null}
        {status.kind === "error" ? (
          <span className="text-down">{status.message}</span>
        ) : null}
        {status.kind === "filled" ? (
          <span className="text-muted">
            <span
              className={status.fill.side === "buy" ? "text-up" : "text-down"}
            >
              FILLED {status.fill.side.toUpperCase()}
            </span>{" "}
            {formatQuantity(status.fill.quantity)} {status.fill.ticker} @{" "}
            <span className="text-ink">{price(status.fill.fill_price)}</span> ·
            total {money(status.fill.total_cost)} · cash{" "}
            {money(status.fill.cash_balance)}
          </span>
        ) : null}
      </div>
    </form>
  );
}
