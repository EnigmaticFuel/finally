import { expect, test } from "@playwright/test";
import { openTerminal, resetPortfolio } from "../helpers";

/** The heatmap's two hues, from Heatmap.tsx cellColor. */
const PROFIT_CHANNEL = "38,194,129";
const LOSS_CHANNEL = "240,69,75";

test.describe("portfolio visualization", () => {
  test.afterEach(async ({ request }) => {
    await resetPortfolio(request);
  });

  test("the heatmap says so when there is nothing to show", async ({ page }) => {
    await openTerminal(page);
    await expect(page.getByTestId("heatmap")).toContainText("NO POSITIONS");
  });

  test("the heatmap draws one cell per position", async ({ page }) => {
    await openTerminal(page);

    for (const ticker of ["AAPL", "NVDA"]) {
      await page.getByTestId("trade-ticker").fill(ticker);
      await page.getByTestId("trade-quantity").fill("2");
      await page.getByTestId("trade-buy").click();
      await expect(page.getByTestId(`positions-row-${ticker}`)).toBeVisible();
    }

    // HeatCell skips the treemap root (depth 0), so the rect count is exactly
    // the position count.
    await expect(page.locator('[data-testid="heatmap"] svg rect')).toHaveCount(
      2,
    );
    await expect(page.getByTestId("heatmap")).toContainText("AAPL");
    await expect(page.getByTestId("heatmap")).toContainText("NVDA");
  });

  test("heatmap cell colour follows the sign of the position P&L", async ({
    page,
  }) => {
    await openTerminal(page);

    await page.getByTestId("trade-ticker").fill("TSLA");
    await page.getByTestId("trade-quantity").fill("2");
    await page.getByTestId("trade-buy").click();
    await expect(page.getByTestId("positions-row-TSLA")).toBeVisible();
    // One position, one rect: the treemap root is not painted.
    await expect(page.locator('[data-testid="heatmap"] svg rect')).toHaveCount(1);

    // Prices move every 500ms and the P&L sign can flip between frames, so the
    // cell fill and the P&L figure are read in one synchronous DOM pass. React
    // renders both from the same commit, which makes the comparison stable.
    const snapshot = await page.evaluate(() => {
      const rect = document.querySelector('[data-testid="heatmap"] svg rect');
      const pnl = document.querySelector('[data-testid="position-pnl-TSLA"]');
      return {
        fill: rect?.getAttribute("fill") ?? "",
        pnl: pnl?.textContent ?? "",
      };
    });

    expect(snapshot.fill).toMatch(/^rgba\(/);
    const profitable = !snapshot.pnl.trim().startsWith("-");
    const expected = profitable ? PROFIT_CHANNEL : LOSS_CHANNEL;
    expect(
      snapshot.fill,
      `P&L was "${snapshot.pnl}" so the cell should use ${expected}`,
    ).toContain(expected);
  });

  test("the P&L chart draws a line with data points", async ({ page }) => {
    await openTerminal(page);

    const chart = page.getByTestId("pnl-chart");
    await expect(chart).not.toContainText("AWAITING SNAPSHOTS");

    const line = chart.locator("svg path.recharts-line-curve");
    await expect(line).toBeAttached();

    const drawn = await line.getAttribute("d");
    expect(drawn, "the P&L line should have a path").toBeTruthy();
    expect(
      (drawn ?? "").split(/[LC]/).length,
      "the P&L line should join at least two snapshots",
    ).toBeGreaterThan(1);
  });

  test("a trade adds a snapshot to the P&L history", async ({
    page,
    request,
  }) => {
    const before = await (await request.get("/api/portfolio/history")).json();

    await openTerminal(page);
    await page.getByTestId("trade-ticker").fill("META");
    await page.getByTestId("trade-quantity").fill("1");
    await page.getByTestId("trade-buy").click();
    await expect(page.getByTestId("positions-row-META")).toBeVisible();

    const after = await (await request.get("/api/portfolio/history")).json();
    expect(after.snapshots.length).toBeGreaterThan(before.snapshots.length);
  });

  test("the main chart renders for the selected ticker", async ({ page }) => {
    await openTerminal(page);

    await page.getByTestId("watchlist-row-GOOGL").click();

    const chart = page.getByTestId("main-chart");
    await expect(chart).toBeVisible();
    await expect(chart).not.toContainText("SELECT A TICKER");
    // MainChart is an AreaChart, so its curve carries the area class.
    await expect(chart.locator("svg path.recharts-area-curve")).toBeAttached();
  });
});
