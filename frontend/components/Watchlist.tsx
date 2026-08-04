"use client";

import { useState, type FormEvent } from "react";
import { Panel } from "./Panel";
import { PriceCell } from "./PriceCell";
import { Sparkline } from "./Sparkline";
import { percent, toneClass } from "@/lib/format";
import type { PriceMap, WatchlistTicker } from "@/lib/types";
import type { SeriesMap } from "@/lib/useSeries";

export function Watchlist({
  entries,
  prices,
  series,
  selected,
  error,
  onSelect,
  onAdd,
  onRemove,
}: {
  entries: WatchlistTicker[];
  prices: PriceMap;
  series: SeriesMap;
  selected: string | null;
  error: string | null;
  onSelect: (ticker: string) => void;
  onAdd: (ticker: string) => void;
  onRemove: (ticker: string) => void;
}) {
  const [draft, setDraft] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    const ticker = draft.trim().toUpperCase();
    if (!ticker) return;
    onAdd(ticker);
    setDraft("");
  }

  return (
    <Panel
      label="watchlist"
      accent="azure"
      meta={`${entries.length}`}
      className="h-full"
      bodyClassName="flex flex-col"
    >
      <div className="flex h-6 shrink-0 items-center gap-2 border-b border-line px-2 text-[9px] tracking-[0.14em] text-dim uppercase">
        <span className="w-12">Sym</span>
        <span className="w-[76px]">Trend</span>
        <span className="ml-auto w-16 text-right">Last</span>
        <span className="w-16 text-right">Chg</span>
        <span className="w-4" />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {entries.length === 0 ? (
          <p
            data-testid="watchlist-empty"
            className="px-2 py-6 text-center text-[11px] tracking-[0.14em] text-dim"
          >
            NO TICKERS
          </p>
        ) : (
          entries.map((entry) => {
            const quote = prices[entry.ticker];
            const last = quote ? quote.price : entry.price;
            const change = quote
              ? quote.change_from_open_percent
              : entry.change_from_open_percent;
            const active = selected === entry.ticker;

            return (
              <div
                key={entry.ticker}
                data-testid={`watchlist-row-${entry.ticker}`}
                onClick={() => onSelect(entry.ticker)}
                className={`flex h-[30px] cursor-pointer items-center gap-2 border-l-2 px-2 text-[12px] hover:bg-raise ${
                  active
                    ? "border-azure bg-raise text-ink"
                    : "border-transparent text-ink"
                }`}
              >
                <span className="w-12 tracking-wide">{entry.ticker}</span>
                <Sparkline
                  points={series[entry.ticker] ?? entry.history}
                  positive={change >= 0}
                  testId={`sparkline-${entry.ticker}`}
                />
                <PriceCell
                  value={last}
                  testId={`watchlist-price-${entry.ticker}`}
                  className="ml-auto w-16 text-right"
                />
                <span
                  data-testid={`watchlist-change-${entry.ticker}`}
                  className={`w-16 text-right ${toneClass(change)}`}
                >
                  {percent(change)}
                </span>
                <button
                  type="button"
                  aria-label={`Remove ${entry.ticker}`}
                  data-testid={`watchlist-remove-${entry.ticker}`}
                  onClick={(event) => {
                    event.stopPropagation();
                    onRemove(entry.ticker);
                  }}
                  className="w-4 text-dim hover:text-down"
                >
                  x
                </button>
              </div>
            );
          })
        )}
      </div>

      {error ? (
        <p
          data-testid="watchlist-error"
          className="shrink-0 border-t border-line px-2 py-1.5 text-[11px] text-down"
        >
          {error}
        </p>
      ) : null}

      <form
        onSubmit={submit}
        className="flex shrink-0 items-center gap-1.5 border-t border-line bg-rail p-1.5"
      >
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="ADD SYMBOL"
          aria-label="Add symbol"
          data-testid="watchlist-add-input"
          className="min-w-0 flex-1 bg-void px-2 py-1 text-[12px] tracking-wide text-ink uppercase outline-none placeholder:text-dim placeholder:tracking-[0.14em]"
        />
        <button
          type="submit"
          data-testid="watchlist-add-button"
          className="bg-plum px-2.5 py-1 text-[10px] tracking-[0.14em] text-ink uppercase hover:brightness-125"
        >
          Add
        </button>
      </form>
    </Panel>
  );
}
