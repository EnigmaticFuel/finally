import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePriceStream } from "@/lib/usePriceStream";
import { FakeEventSource, priceMap, quote } from "./fakes";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

/** Advance both the liveness interval and the clock it reads. */
function tick(ms: number) {
  act(() => void vi.advanceTimersByTime(ms));
}

describe("usePriceStream", () => {
  it("subscribes to the one live channel", () => {
    renderHook(() => usePriceStream());
    expect(FakeEventSource.last.url).toBe("/api/stream/prices");
  });

  it("starts degraded while the connection is opening", () => {
    const { result } = renderHook(() => usePriceStream());
    expect(result.current.status).toBe("degraded");
  });

  it("goes live once the connection opens", () => {
    const { result } = renderHook(() => usePriceStream());
    FakeEventSource.last.open();
    expect(result.current.status).toBe("live");
  });

  it("parses one event as a map of every ticker, keyed by symbol", () => {
    const { result } = renderHook(() => usePriceStream());
    FakeEventSource.last.open();
    FakeEventSource.last.emit(
      priceMap(quote("AAPL", 190.5, 0.687), quote("TSLA", 240, -1.25)),
    );

    expect(Object.keys(result.current.prices).sort()).toEqual(["AAPL", "TSLA"]);
    expect(result.current.prices.AAPL.price).toBe(190.5);
    expect(result.current.prices.TSLA.change_from_open_percent).toBe(-1.25);
  });

  it("replaces the map on each frame rather than merging stale tickers", () => {
    const { result } = renderHook(() => usePriceStream());
    FakeEventSource.last.open();
    FakeEventSource.last.emit(priceMap(quote("AAPL", 190), quote("TSLA", 240)));
    FakeEventSource.last.emit(priceMap(quote("AAPL", 191)));

    expect(Object.keys(result.current.prices)).toEqual(["AAPL"]);
  });

  it("degrades while reconnecting after an error", () => {
    const { result } = renderHook(() => usePriceStream());
    FakeEventSource.last.open();
    FakeEventSource.last.fail(FakeEventSource.CONNECTING);
    expect(result.current.status).toBe("degraded");
  });

  it("goes down when the browser closes the connection for good", () => {
    const { result } = renderHook(() => usePriceStream());
    FakeEventSource.last.open();
    FakeEventSource.last.fail(FakeEventSource.CLOSED);
    expect(result.current.status).toBe("down");
  });

  it("degrades after 30s of silence on an open connection", () => {
    const { result } = renderHook(() => usePriceStream());
    FakeEventSource.last.open();

    tick(29_000);
    expect(result.current.status).toBe("live");

    tick(2_000);
    expect(result.current.status).toBe("degraded");
  });

  it("returns to live when a frame arrives after silence", () => {
    const { result } = renderHook(() => usePriceStream());
    FakeEventSource.last.open();
    tick(31_000);
    expect(result.current.status).toBe("degraded");

    FakeEventSource.last.emit(priceMap(quote("AAPL", 190)));
    expect(result.current.status).toBe("live");
  });

  it("closes the connection on unmount", () => {
    const { unmount } = renderHook(() => usePriceStream());
    const source = FakeEventSource.last;
    unmount();
    expect(source.closed).toBe(true);
  });
});
