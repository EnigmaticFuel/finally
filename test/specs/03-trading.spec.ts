import { expect, test } from "@playwright/test";
import { openTerminal, parseMoney, readCash, resetPortfolio } from "../helpers";

const TICKER = "MSFT";

test.describe("trading", () => {
  test.afterEach(async ({ request }) => {
    await resetPortfolio(request);
  });

  async function trade(
    page: import("@playwright/test").Page,
    quantity: string,
    side: "buy" | "sell",
  ): Promise<void> {
    await page.getByTestId("trade-ticker").fill(TICKER);
    await page.getByTestId("trade-quantity").fill(quantity);
    await page.getByTestId(`trade-${side}`).click();
    await expect(page.getByTestId("trade-status")).toContainText(
      new RegExp(`FILLED ${side}`, "i"),
    );
  }

  test("a buy decreases cash, opens a position and reports the fill price", async ({
    page,
  }) => {
    await openTerminal(page);
    const cashBefore = await readCash(page);

    await trade(page, "3", "buy");

    // The fill price is the server's, so the bar must report a concrete number
    // rather than echoing whatever was on screen when the button was pressed.
    const status = page.getByTestId("trade-status");
    await expect(status).toContainText(/FILLED BUY 3 MSFT @ \d+\.\d{2}/);

    const fill = Number(
      (await status.innerText()).match(/@ (\d+\.\d{2})/)?.[1] ?? "0",
    );
    expect(fill).toBeGreaterThan(0);

    const row = page.getByTestId(`positions-row-${TICKER}`);
    await expect(row).toBeVisible();
    await expect(row).toContainText("3");
    await expect(page.getByTestId("positions-empty")).toBeHidden();

    // Cash falls by roughly the notional. Not exactly, because the header
    // reads back the server's balance after the server's own fill price.
    const cashAfter = await readCash(page);
    expect(cashAfter).toBeLessThan(cashBefore);
    expect(cashBefore - cashAfter).toBeCloseTo(fill * 3, 1);
  });

  test("the reported fill price matches what the server recorded", async ({
    page,
  }) => {
    await openTerminal(page);
    await trade(page, "2", "buy");

    const status = await page.getByTestId("trade-status").innerText();
    const shown = Number(status.match(/@ (\d+\.\d{2})/)?.[1] ?? "0");

    const portfolio = await (
      await page.request.get("/api/portfolio")
    ).json();
    const position = portfolio.positions.find(
      (entry: { ticker: string }) => entry.ticker === TICKER,
    );

    expect(position).toBeDefined();
    expect(position.avg_cost).toBeCloseTo(shown, 2);
  });

  test("a partial sell increases cash and leaves the position open", async ({
    page,
  }) => {
    await openTerminal(page);
    await trade(page, "4", "buy");
    await expect(page.getByTestId(`positions-row-${TICKER}`)).toContainText("4");

    const cashBefore = await readCash(page);
    await trade(page, "1", "sell");

    const row = page.getByTestId(`positions-row-${TICKER}`);
    await expect(row).toBeVisible();
    await expect(row).toContainText("3");

    await expect
      .poll(() => readCash(page))
      .toBeGreaterThan(cashBefore);
    await expect(page.getByTestId("trade-status")).toContainText(
      /FILLED SELL 1 MSFT @ \d+\.\d{2}/,
    );
  });

  test("selling the whole position removes the row entirely", async ({
    page,
  }) => {
    await openTerminal(page);
    await trade(page, "2", "buy");
    await expect(page.getByTestId(`positions-row-${TICKER}`)).toBeVisible();

    await trade(page, "2", "sell");

    await expect(page.getByTestId(`positions-row-${TICKER}`)).toBeHidden();
    await expect(page.getByTestId("positions-empty")).toBeVisible();
  });

  test("selling more than is held is rejected with a visible error", async ({
    page,
  }) => {
    await openTerminal(page);
    await trade(page, "1", "buy");

    await page.getByTestId("trade-quantity").fill("50");
    await page.getByTestId("trade-sell").click();

    await expect(page.getByTestId("trade-status")).toContainText(
      /insufficient shares/i,
    );
    await expect(page.getByTestId(`positions-row-${TICKER}`)).toContainText("1");
  });

  test("buying beyond the cash balance is rejected with a visible error", async ({
    page,
  }) => {
    await openTerminal(page);

    await page.getByTestId("trade-ticker").fill(TICKER);
    await page.getByTestId("trade-quantity").fill("100000");
    await page.getByTestId("trade-buy").click();

    await expect(page.getByTestId("trade-status")).toContainText(
      /insufficient cash/i,
    );
    await expect(page.getByTestId("positions-empty")).toBeVisible();
  });

  test("the header total tracks cash plus the live value of positions", async ({
    page,
  }) => {
    await openTerminal(page);
    await trade(page, "5", "buy");

    // Live prices move on every frame, so this asserts the relationship
    // between the numbers within a single DOM read rather than a fixed value.
    const consistent = await page.evaluate(() => {
      const read = (id: string) =>
        document.querySelector(`[data-testid="${id}"]`)?.textContent ?? "";
      return { total: read("header-total"), cash: read("header-cash") };
    });

    const total = parseMoney(consistent.total);
    const cash = parseMoney(consistent.cash);
    expect(total).toBeGreaterThan(cash);
  });
});
