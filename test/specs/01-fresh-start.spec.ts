import { expect, test } from "@playwright/test";
import {
  DEFAULT_TICKERS,
  STARTING_CASH,
  curvePoints,
  openTerminal,
  readCash,
  readTotal,
  waitForLiveStream,
} from "../helpers";

/**
 * The first thing a user sees. This file runs first in the suite because it is
 * the only one that asserts the absolute $10,000 seed balance; global setup
 * has just recreated the database.
 */
test.describe("fresh start", () => {
  test("shows the ten default tickers", async ({ page }) => {
    await openTerminal(page);

    for (const ticker of DEFAULT_TICKERS) {
      await expect(page.getByTestId(`watchlist-row-${ticker}`)).toBeVisible();
    }
    await expect(page.getByTestId("watchlist-empty")).toBeHidden();
  });

  test("shows the seeded $10,000 balance and no positions", async ({ page }) => {
    await openTerminal(page);

    await expect(page.getByTestId("header-cash")).toHaveText("$10,000.00");
    await expect(page.getByTestId("positions-empty")).toBeVisible();

    // Nothing is invested, so the total value is exactly the cash balance and
    // does not drift with the stream.
    await expect(page.getByTestId("header-total")).toHaveText("$10,000.00");
    expect(await readCash(page)).toBe(STARTING_CASH);
    expect(await readTotal(page)).toBe(STARTING_CASH);
  });

  test("streams prices into the watchlist", async ({ page }) => {
    await openTerminal(page);

    const price = page.getByTestId("watchlist-price-AAPL");
    await expect(price).not.toBeEmpty();
    const first = await price.innerText();

    // The simulator ticks every 500ms. Wait on the value changing rather than
    // on the clock.
    await expect
      .poll(() => price.innerText(), { timeout: 20_000 })
      .not.toBe(first);
  });

  test("reports the stream as live in the header", async ({ page }) => {
    await openTerminal(page);
    await expect(page.getByTestId("connection-dot")).toHaveAttribute(
      "data-status",
      "live",
    );
  });

  test("seeds sparklines from the watchlist response when no price event arrives", async ({
    page,
  }) => {
    // Blocking the stream isolates the seeding path: with no SSE frames at
    // all, any line in a sparkline must have come from the ~60 history points
    // GET /api/watchlist returns.
    await page.route("**/api/stream/prices", (route) => route.abort());
    await page.goto("/");

    const line = page.locator('[data-testid="sparkline-AAPL"] svg path').first();
    await expect(line).toBeAttached();
    expect(curvePoints(await line.getAttribute("d"))).toBeGreaterThanOrEqual(50);
  });

  test("paints populated sparklines on first paint with the stream live", async ({
    page,
  }) => {
    // The scenario as a user meets it (PLAN.md sections 2 and 12): the
    // sparklines are already drawn from history on first paint rather than
    // filling in over the first 30 seconds of streaming.
    await page.goto("/");
    await expect(page.getByTestId("watchlist-row-AAPL")).toBeVisible();
    await waitForLiveStream(page);

    const line = page.locator('[data-testid="sparkline-AAPL"] svg path').first();
    await expect(line).toBeAttached();
    expect(
      curvePoints(await line.getAttribute("d")),
      "the sparkline should be seeded with history, not accumulated from the stream",
    ).toBeGreaterThanOrEqual(50);
  });

  test("the main chart is drawn from history on first paint", async ({
    page,
  }) => {
    await openTerminal(page);

    const curve = page.locator(
      '[data-testid="main-chart"] svg path.recharts-area-curve',
    );
    await expect(curve).toBeAttached();
    expect(curvePoints(await curve.getAttribute("d"))).toBeGreaterThanOrEqual(
      50,
    );
  });

  test("serves sparkline history for every default ticker", async ({
    request,
  }) => {
    const body = await (await request.get("/api/watchlist")).json();
    expect(body.tickers).toHaveLength(DEFAULT_TICKERS.length);

    for (const entry of body.tickers) {
      expect(
        entry.history.length,
        `${entry.ticker} should arrive with sparkline history`,
      ).toBeGreaterThanOrEqual(50);
      expect(entry.price).toBeGreaterThan(0);
    }
  });
});
