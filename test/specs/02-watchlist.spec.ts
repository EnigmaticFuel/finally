import { expect, test } from "@playwright/test";
import { openTerminal, resetPortfolio } from "../helpers";

const NEW_TICKER = "PYPL";

test.describe("watchlist", () => {
  test.afterEach(async ({ request }) => {
    await resetPortfolio(request);
  });

  test("adds a ticker and starts its price feed", async ({ page }) => {
    await openTerminal(page);
    await expect(page.getByTestId(`watchlist-row-${NEW_TICKER}`)).toBeHidden();

    await page.getByTestId("watchlist-add-input").fill(NEW_TICKER);
    await page.getByTestId("watchlist-add-button").click();

    const row = page.getByTestId(`watchlist-row-${NEW_TICKER}`);
    await expect(row).toBeVisible();
    await expect(page.getByTestId("watchlist-error")).toBeHidden();

    // An added ticker is only useful if it is actually being priced.
    const price = page.getByTestId(`watchlist-price-${NEW_TICKER}`);
    await expect(price).not.toBeEmpty();
    const first = await price.innerText();
    await expect
      .poll(() => price.innerText(), { timeout: 20_000 })
      .not.toBe(first);
  });

  test("removes a ticker", async ({ page }) => {
    await openTerminal(page);

    await page.getByTestId("watchlist-add-input").fill(NEW_TICKER);
    await page.getByTestId("watchlist-add-button").click();
    await expect(page.getByTestId(`watchlist-row-${NEW_TICKER}`)).toBeVisible();

    await page.getByTestId(`watchlist-remove-${NEW_TICKER}`).click();

    await expect(page.getByTestId(`watchlist-row-${NEW_TICKER}`)).toBeHidden();
    await expect(page.getByTestId("watchlist-error")).toBeHidden();
  });

  test("rejects a malformed symbol with a visible error", async ({ page }) => {
    await openTerminal(page);

    await page.getByTestId("watchlist-add-input").fill("TOOLONG");
    await page.getByTestId("watchlist-add-button").click();

    await expect(page.getByTestId("watchlist-error")).toBeVisible();
    await expect(page.getByTestId("watchlist-row-TOOLONG")).toBeHidden();
  });

  test("refuses to remove a ticker with an open position", async ({ page }) => {
    await openTerminal(page);

    await page.getByTestId("trade-ticker").fill("JPM");
    await page.getByTestId("trade-quantity").fill("1");
    await page.getByTestId("trade-buy").click();
    await expect(page.getByTestId("positions-row-JPM")).toBeVisible();

    await page.getByTestId("watchlist-remove-JPM").click();

    const error = page.getByTestId("watchlist-error");
    await expect(error).toBeVisible();
    await expect(error).toContainText(/cannot remove jpm/i);
    await expect(page.getByTestId("watchlist-row-JPM")).toBeVisible();
  });

  test("returns 409 from the API when a position is held", async ({
    request,
  }) => {
    await request.post("/api/portfolio/trade", {
      data: { ticker: "JPM", quantity: 1, side: "buy" },
    });

    const response = await request.delete("/api/watchlist/JPM");

    expect(response.status()).toBe(409);
    expect((await response.json()).detail).toMatch(/cannot remove jpm/i);
  });

  test("trading an unwatched ticker adds it to the watchlist", async ({
    page,
    request,
  }) => {
    await request.delete("/api/watchlist/NFLX");
    await openTerminal(page);
    await expect(page.getByTestId("watchlist-row-NFLX")).toBeHidden();

    await page.getByTestId("trade-ticker").fill("NFLX");
    await page.getByTestId("trade-quantity").fill("1");
    await page.getByTestId("trade-buy").click();

    await expect(page.getByTestId("positions-row-NFLX")).toBeVisible();
    await expect(page.getByTestId("watchlist-row-NFLX")).toBeVisible();
  });
});
