/** Test doubles: a controllable EventSource and the mock payloads the panels
    are fed. Nothing here talks to a real backend. */

import { act } from "@testing-library/react";
import { vi } from "vitest";
import type {
  ChatMessage,
  Portfolio,
  PriceMap,
  PriceUpdate,
  Snapshot,
  WatchlistTicker,
} from "@/lib/types";

export class FakeEventSource {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;
  static instances: FakeEventSource[] = [];

  readyState = FakeEventSource.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  static get last(): FakeEventSource {
    return FakeEventSource.instances[FakeEventSource.instances.length - 1];
  }

  close() {
    this.closed = true;
    this.readyState = FakeEventSource.CLOSED;
  }

  open() {
    this.readyState = FakeEventSource.OPEN;
    act(() => this.onopen?.());
  }

  /** One event carries every ticker, keyed by symbol. */
  emit(prices: PriceMap) {
    this.readyState = FakeEventSource.OPEN;
    act(() =>
      this.onmessage?.({ data: JSON.stringify(prices) } as MessageEvent),
    );
  }

  fail(readyState: number) {
    this.readyState = readyState;
    act(() => this.onerror?.());
  }
}

export function quote(
  ticker: string,
  price: number,
  changeFromOpenPercent = 0,
): PriceUpdate {
  const open = price / (1 + changeFromOpenPercent / 100);
  return {
    ticker,
    price,
    previous_price: price,
    open_price: open,
    timestamp: 1753401234.5,
    change: price - open,
    change_percent: 0,
    change_from_open_percent: changeFromOpenPercent,
    direction: changeFromOpenPercent >= 0 ? "up" : "down",
  };
}

export function priceMap(...updates: PriceUpdate[]): PriceMap {
  return Object.fromEntries(updates.map((update) => [update.ticker, update]));
}

export function watchlistTicker(
  ticker: string,
  price: number,
  changeFromOpenPercent = 0,
): WatchlistTicker {
  const open = price / (1 + changeFromOpenPercent / 100);
  return {
    ticker,
    price,
    open_price: open,
    change_from_open_percent: changeFromOpenPercent,
    history: Array.from({ length: 60 }, (_, i) => open + i * 0.01),
  };
}

export const samplePortfolio: Portfolio = {
  cash_balance: 8234.5,
  total_value: 10139.5,
  positions: [
    {
      ticker: "AAPL",
      quantity: 10,
      avg_cost: 188.6,
      current_price: 190.5,
      market_value: 1905,
      unrealized_pnl: 19,
      unrealized_pnl_percent: 1.007,
    },
  ],
};

export const sampleSnapshots: Snapshot[] = [
  { total_value: 10120.75, recorded_at: "2026-07-25T14:01:00Z" },
  { total_value: 10000, recorded_at: "2026-07-25T14:00:00Z" },
];

export const sampleMessages: ChatMessage[] = [
  {
    role: "user",
    content: "buy 1 AAPL",
    actions: null,
    created_at: "2026-07-25T14:02:00Z",
  },
  {
    role: "assistant",
    content: "Bought 1 share of AAPL.",
    actions: {
      trades: [{ ticker: "AAPL", side: "buy", quantity: 1 }],
      watchlist_changes: [],
    },
    created_at: "2026-07-25T14:02:01Z",
  },
];

type Route = unknown | ((init?: RequestInit) => unknown);

const FAILURE = Symbol("failure");

interface Failure {
  [FAILURE]: true;
  status: number;
  detail: string;
}

/** A route that answers with the backend's error envelope. */
export function failWith(status: number, detail: string): Failure {
  return { [FAILURE]: true, status, detail };
}

function json(body: unknown, status: number) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Route each path prefix to a JSON body, longest prefix first so
    /api/portfolio/history wins over /api/portfolio. An unrouted path 404s,
    which is how the empty-state tests are driven. */
export function mockFetch(routes: Record<string, Route>) {
  const prefixes = Object.keys(routes).sort((a, b) => b.length - a.length);

  return vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const key = prefixes.find((route) => url.startsWith(route));
    if (key === undefined) return json({ detail: `No route for ${url}` }, 404);

    const body = routes[key];
    const value =
      typeof body === "function"
        ? (body as (init?: RequestInit) => unknown)(init)
        : body;

    const failure = value as Failure;
    if (failure && failure[FAILURE]) {
      return json({ detail: failure.detail }, failure.status);
    }
    return json(value, 200);
  });
}

/** How many times a path was requested with a given method, matched exactly.
    Defaults to GET so a POST and the refetch that follows it stay countable
    apart, since both land on the same URL. */
export function callCount(
  fetchMock: ReturnType<typeof mockFetch>,
  path: string,
  method = "GET",
): number {
  return fetchMock.mock.calls.filter(
    (call) => call[0] === path && (call[1]?.method ?? "GET") === method,
  ).length;
}
