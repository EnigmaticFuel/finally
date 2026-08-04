"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ChatPanel } from "@/components/ChatPanel";
import { Header } from "@/components/Header";
import { Heatmap } from "@/components/Heatmap";
import { MainChart } from "@/components/MainChart";
import { PnlChart } from "@/components/PnlChart";
import { PositionsTable } from "@/components/PositionsTable";
import { TradeBar } from "@/components/TradeBar";
import { Watchlist } from "@/components/Watchlist";
import {
  addWatchlistTicker,
  executeTrade,
  fetchChatHistory,
  fetchHistory,
  fetchPortfolio,
  fetchWatchlist,
  removeWatchlistTicker,
  sendChatMessage,
} from "@/lib/api";
import { liveTotalValue, liveUnrealizedPnl, livePositions } from "@/lib/derive";
import { usePriceStream } from "@/lib/usePriceStream";
import { useSeries } from "@/lib/useSeries";
import type {
  ChatMessage,
  Portfolio,
  Snapshot,
  WatchlistTicker,
} from "@/lib/types";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed.";
}

export default function Terminal() {
  const { prices, status } = usePriceStream();

  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistTicker[]>([]);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatOpen, setChatOpen] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [watchlistError, setWatchlistError] = useState<string | null>(null);

  const series = useSeries(watchlist, prices);

  /** A failed fetch leaves the panel empty rather than breaking the terminal. */
  const loadPortfolio = useCallback(async () => {
    try {
      setPortfolio(await fetchPortfolio());
    } catch {
      setPortfolio(null);
    }
  }, []);

  const loadWatchlist = useCallback(async () => {
    try {
      setWatchlist((await fetchWatchlist()).tickers);
    } catch {
      setWatchlist([]);
    }
  }, []);

  const loadSnapshots = useCallback(async () => {
    try {
      setSnapshots((await fetchHistory()).snapshots);
    } catch {
      setSnapshots([]);
    }
  }, []);

  /** The one refetch rule: after a manual trade, and after a chat response
      that changed server state. There is no polling loop. */
  const refresh = useCallback(async () => {
    await Promise.all([loadPortfolio(), loadWatchlist(), loadSnapshots()]);
  }, [loadPortfolio, loadWatchlist, loadSnapshots]);

  useEffect(() => {
    void refresh();
    fetchChatHistory()
      .then((body) => setMessages(body.messages))
      .catch(() => setMessages([]));
  }, [refresh]);

  useEffect(() => {
    if (!selected && watchlist.length > 0) setSelected(watchlist[0].ticker);
  }, [watchlist, selected]);

  const positions = useMemo(
    () => livePositions(portfolio?.positions ?? [], prices),
    [portfolio, prices],
  );
  const totalValue = useMemo(
    () => liveTotalValue(portfolio, prices),
    [portfolio, prices],
  );
  const unrealized = useMemo(() => liveUnrealizedPnl(positions), [positions]);

  const handleTrade = useCallback(
    async (ticker: string, amount: number, side: "buy" | "sell") => {
      const fill = await executeTrade(ticker, amount, side);
      await refresh();
      return fill;
    },
    [refresh],
  );

  const handleAdd = useCallback(
    async (ticker: string) => {
      try {
        await addWatchlistTicker(ticker);
        setWatchlistError(null);
        await loadWatchlist();
      } catch (error) {
        setWatchlistError(errorMessage(error));
      }
    },
    [loadWatchlist],
  );

  const handleRemove = useCallback(
    async (ticker: string) => {
      try {
        await removeWatchlistTicker(ticker);
        setWatchlistError(null);
        if (selected === ticker) setSelected(null);
        await loadWatchlist();
      } catch (error) {
        setWatchlistError(errorMessage(error));
      }
    },
    [loadWatchlist, selected],
  );

  const handleSend = useCallback(
    async (text: string) => {
      const now = new Date().toISOString();
      setMessages((current) => [
        ...current,
        { role: "user", content: text, actions: null, created_at: now },
      ]);
      setChatLoading(true);
      try {
        const response = await sendChatMessage(text);
        setMessages((current) => [
          ...current,
          {
            role: "assistant",
            content: response.message,
            actions: {
              trades: response.trades,
              watchlist_changes: response.watchlist_changes,
            },
            created_at: new Date().toISOString(),
          },
        ]);
        if (
          response.trades.length > 0 ||
          response.watchlist_changes.length > 0
        ) {
          await refresh();
        }
      } catch (error) {
        setMessages((current) => [
          ...current,
          {
            role: "assistant",
            content: errorMessage(error),
            actions: null,
            created_at: new Date().toISOString(),
          },
        ]);
      } finally {
        setChatLoading(false);
      }
    },
    [refresh],
  );

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-void text-[13px] text-ink">
      <Header
        cash={portfolio?.cash_balance ?? 0}
        totalValue={totalValue}
        unrealizedPnl={unrealized}
        status={status}
      />

      <div className="flex min-h-0 flex-1">
        <div className="w-[300px] shrink-0 border-r border-line">
          <Watchlist
            entries={watchlist}
            prices={prices}
            series={series}
            selected={selected}
            error={watchlistError}
            onSelect={setSelected}
            onAdd={(ticker) => void handleAdd(ticker)}
            onRemove={(ticker) => void handleRemove(ticker)}
          />
        </div>

        <main className="flex min-w-0 flex-1 flex-col">
          <MainChart
            ticker={selected}
            points={selected ? (series[selected] ?? []) : []}
            quote={selected ? prices[selected] : undefined}
          />
          <div className="flex h-[210px] shrink-0 border-t border-line">
            <Heatmap positions={positions} />
            <PnlChart snapshots={snapshots} liveValue={totalValue} />
          </div>
          <div className="h-[200px] shrink-0 border-t border-line">
            <PositionsTable positions={positions} onSelect={setSelected} />
          </div>
        </main>

        <ChatPanel
          messages={messages}
          loading={chatLoading}
          collapsed={!chatOpen}
          onToggle={() => setChatOpen((open) => !open)}
          onSend={(text) => void handleSend(text)}
        />
      </div>

      <TradeBar selected={selected} onSubmit={handleTrade} />
    </div>
  );
}
