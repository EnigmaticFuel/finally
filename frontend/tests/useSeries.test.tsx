import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useSeries } from "@/lib/useSeries";
import type { PriceMap, WatchlistTicker } from "@/lib/types";
import { priceMap, quote, watchlistTicker } from "./fakes";

const aapl = watchlistTicker("AAPL", 190.5, 0.687);

function renderSeries(watchlist: WatchlistTicker[], prices: PriceMap = {}) {
  return renderHook(
    ({ w, p }: { w: WatchlistTicker[]; p: PriceMap }) => useSeries(w, p),
    { initialProps: { w: watchlist, p: prices } },
  );
}

describe("useSeries", () => {
  it("seeds from the watchlist history so a sparkline is never empty", () => {
    const { result } = renderSeries([aapl]);
    expect(result.current.AAPL).toHaveLength(60);
    expect(result.current.AAPL).toEqual(aapl.history);
  });

  it("extends the seeded series from the stream", () => {
    const { result, rerender } = renderSeries([aapl]);
    rerender({ w: [aapl], p: priceMap(quote("AAPL", 195)) });

    expect(result.current.AAPL).toHaveLength(61);
    expect(result.current.AAPL.at(-1)).toBe(195);
  });

  it("seeds history when the stream frame lands before the watchlist fetch", () => {
    // What the browser actually does: the SSE generator emits a full cache
    // snapshot at connect, which beats the /api/watchlist response.
    const frame = priceMap(quote("AAPL", 195));
    const { result, rerender } = renderSeries([], frame);
    expect(result.current.AAPL).toEqual([195]);

    rerender({ w: [aapl], p: frame });

    expect(result.current.AAPL).toEqual([...aapl.history, 195]);
  });

  it("seeds a ticker the stream reached before the watchlist refetch", () => {
    // The AI adds PYPL: the backend streams it right away, and the refetch
    // that follows the chat response is what carries its history.
    const frame = priceMap(quote("AAPL", 195), quote("PYPL", 70));
    const { result, rerender } = renderSeries([aapl]);
    rerender({ w: [aapl], p: frame });

    const pypl = watchlistTicker("PYPL", 70, 0.5);
    rerender({ w: [aapl, pypl], p: frame });

    expect(result.current.PYPL).toEqual([...pypl.history, 70]);
    expect(result.current.AAPL).toHaveLength(61);
  });

  it("does not reset an extended series when the watchlist is refetched", () => {
    // One frame, one point: the same map object stands for the same tick.
    const frame = priceMap(quote("AAPL", 195));
    const { result, rerender } = renderSeries([aapl]);
    rerender({ w: [aapl], p: frame });

    rerender({ w: [watchlistTicker("AAPL", 195, 3)], p: frame });
    rerender({ w: [watchlistTicker("AAPL", 195, 4)], p: frame });

    expect(result.current.AAPL).toEqual([...aapl.history, 195]);
  });

  it("seeds a ticker added after first paint", () => {
    const { result, rerender } = renderSeries([aapl]);
    const pypl = watchlistTicker("PYPL", 70, 0.5);
    rerender({ w: [aapl, pypl], p: {} });

    expect(result.current.PYPL).toEqual(pypl.history);
  });

  it("caps the series so it cannot grow without bound", () => {
    const long = { ...aapl, history: Array.from({ length: 500 }, (_, i) => i) };
    const { result } = renderSeries([long]);
    expect(result.current.AAPL).toHaveLength(240);
    expect(result.current.AAPL[0]).toBe(260);
  });
});
