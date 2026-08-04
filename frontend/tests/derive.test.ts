import { describe, expect, it } from "vitest";
import {
  livePositions,
  livePrice,
  liveTotalValue,
  liveUnrealizedPnl,
} from "@/lib/derive";
import type { Portfolio, Position } from "@/lib/types";
import { priceMap, quote, samplePortfolio } from "./fakes";

const aapl: Position = {
  ticker: "AAPL",
  quantity: 10,
  avg_cost: 100,
  current_price: 110,
  market_value: 1100,
  unrealized_pnl: 100,
  unrealized_pnl_percent: 10,
};

const tsla: Position = {
  ticker: "TSLA",
  quantity: 5,
  avg_cost: 200,
  current_price: 180,
  market_value: 900,
  unrealized_pnl: -100,
  unrealized_pnl_percent: -10,
};

describe("livePrice", () => {
  it("prefers the streamed price", () => {
    expect(livePrice(priceMap(quote("AAPL", 123)), "AAPL", 99)).toBe(123);
  });

  it("falls back to the server value when the stream has no tick yet", () => {
    expect(livePrice({}, "AAPL", 99)).toBe(99);
  });
});

describe("livePositions", () => {
  it("reprices against the stream rather than the server snapshot", () => {
    const [position] = livePositions([aapl], priceMap(quote("AAPL", 120)));
    expect(position.live_price).toBe(120);
    expect(position.live_market_value).toBe(1200);
    expect(position.live_pnl).toBe(200);
    expect(position.live_pnl_percent).toBeCloseTo(20);
  });

  it("computes weight as a share of invested value", () => {
    const priced = livePositions(
      [aapl, tsla],
      priceMap(quote("AAPL", 100), quote("TSLA", 100)),
    );
    expect(priced[0].weight).toBeCloseTo(66.667, 2);
    expect(priced[1].weight).toBeCloseTo(33.333, 2);
  });

  it("reports a loss when the live price is below cost", () => {
    const [position] = livePositions([tsla], priceMap(quote("TSLA", 150)));
    expect(position.live_pnl).toBe(-250);
    expect(position.live_pnl_percent).toBeCloseTo(-25);
  });

  it("returns nothing for an empty portfolio", () => {
    expect(livePositions([], {})).toEqual([]);
  });
});

describe("liveTotalValue", () => {
  it("is cash plus quantity times live price", () => {
    const portfolio: Portfolio = {
      cash_balance: 1000,
      total_value: 3000,
      positions: [aapl, tsla],
    };
    const prices = priceMap(quote("AAPL", 120), quote("TSLA", 200));
    expect(liveTotalValue(portfolio, prices)).toBe(1000 + 1200 + 1000);
  });

  it("uses the server price for a ticker the stream has not sent", () => {
    expect(liveTotalValue(samplePortfolio, {})).toBeCloseTo(8234.5 + 1905);
  });

  it("is zero before the portfolio loads", () => {
    expect(liveTotalValue(null, {})).toBe(0);
  });
});

describe("liveUnrealizedPnl", () => {
  it("sums P&L across positions", () => {
    const priced = livePositions(
      [aapl, tsla],
      priceMap(quote("AAPL", 110), quote("TSLA", 190)),
    );
    expect(liveUnrealizedPnl(priced)).toBe(100 - 50);
  });
});
