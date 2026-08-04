import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const DEFAULT_TICKERS = [
  "AAPL",
  "GOOGL",
  "MSFT",
  "AMZN",
  "TSLA",
  "NVDA",
  "META",
  "JPM",
  "V",
  "NFLX",
];

export const STARTING_CASH = 10_000;

/** "$8,234.50" and "-$12.30" both become a plain number. */
export function parseMoney(text: string): number {
  const negative = text.trim().startsWith("-");
  const value = Number(text.replace(/[^0-9.]/g, ""));
  expect(Number.isFinite(value), `could not parse money from "${text}"`).toBe(true);
  return negative ? -value : value;
}

/** Reads the header cash figure as a number. */
export async function readCash(page: Page): Promise<number> {
  return parseMoney(await page.getByTestId("header-cash").innerText());
}

/** Reads the header total portfolio value as a number. */
export async function readTotal(page: Page): Promise<number> {
  return parseMoney(await page.getByTestId("header-total").innerText());
}

/** Waits until the price stream is established and the dot is green. */
export async function waitForLiveStream(page: Page): Promise<void> {
  await expect(page.getByTestId("connection-dot")).toHaveAttribute(
    "data-status",
    "live",
    { timeout: 20_000 },
  );
}

/**
 * Loads the terminal and waits for it to be genuinely ready: the watchlist
 * rendered, the stream live, and the portfolio fetch applied. The header shows
 * $0.00 until /api/portfolio resolves, so anything that reads cash must wait
 * for that rather than assume it has landed.
 */
export async function openTerminal(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.getByTestId("watchlist-row-AAPL")).toBeVisible();
  await expect(page.getByTestId("header-total")).not.toHaveText("$0.00");
  await waitForLiveStream(page);
}

/**
 * Number of points behind a recharts monotone curve. Segments are cubic
 * beziers ("C") except a two-point curve, which d3 degenerates to a line
 * ("L"), so both commands are counted.
 */
export function curvePoints(path: string | null): number {
  if (!path) return 0;
  return (path.match(/[CL]/g) ?? []).length + 1;
}

/**
 * Returns the portfolio to the default shape between tests: no positions, and
 * only the ten seeded tickers on the watchlist. Cash is deliberately not
 * restored to exactly $10,000 because prices move between the buy and the
 * sell, so no test after the fresh start asserts an absolute cash figure.
 */
export async function resetPortfolio(request: APIRequestContext): Promise<void> {
  const portfolio = await (await request.get("/api/portfolio")).json();
  for (const position of portfolio.positions) {
    await request.post("/api/portfolio/trade", {
      data: {
        ticker: position.ticker,
        quantity: position.quantity,
        side: "sell",
      },
    });
  }

  const watchlist = await (await request.get("/api/watchlist")).json();
  for (const entry of watchlist.tickers) {
    if (!DEFAULT_TICKERS.includes(entry.ticker)) {
      await request.delete(`/api/watchlist/${entry.ticker}`);
    }
  }
}
