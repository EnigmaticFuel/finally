import { expect, test, type Locator, type Page } from "@playwright/test";
import { openTerminal, readCash, resetPortfolio } from "../helpers";

/**
 * The mock in PLAN.md section 9 is a frozen contract, so these assertions are
 * against the spec rather than against whatever a model happens to say. Global
 * setup refuses to run unless LLM_MOCK=true.
 *
 * Chat history is persistent and shared across this file, so every assertion
 * is scoped to the newest reply rather than to the whole panel.
 */

function lastReply(page: Page): Locator {
  return page.getByTestId("chat-message").last();
}

async function send(page: Page, text: string): Promise<void> {
  const before = await page.getByTestId("chat-message").count();
  await page.getByTestId("chat-input").fill(text);
  await page.getByTestId("chat-send").click();
  await expect(page.getByTestId("chat-message")).toHaveCount(before + 2);
  await expect(page.getByTestId("chat-loading")).toBeHidden();
  await expect(lastReply(page)).toHaveAttribute("data-role", "assistant");
}

test.describe("AI chat with the deterministic mock", () => {
  test.afterEach(async ({ request }) => {
    await resetPortfolio(request);
  });

  test("answers a general question with the analysis contract string", async ({
    page,
  }) => {
    await openTerminal(page);
    await send(page, "how is my portfolio doing");

    const reply = lastReply(page);
    await expect(reply).toContainText(
      /You are holding \d+ positions worth \$[\d,]+\.\d{2} with \$[\d,]+\.\d{2} in cash\./,
    );
    await expect(reply.getByTestId("chat-action-trade")).toHaveCount(0);
    await expect(reply.getByTestId("chat-action-watchlist")).toHaveCount(0);
  });

  test("executes a buy and shows it inline", async ({ page }) => {
    await openTerminal(page);
    const cashBefore = await readCash(page);

    await send(page, "buy NVDA please");

    const chip = lastReply(page).getByTestId("chat-action-trade");
    await expect(chip).toHaveCount(1);
    await expect(chip).toContainText(/buy 1 NVDA/i);

    // The mock routes through the real execution path, so the portfolio must
    // actually have moved.
    await expect(page.getByTestId("positions-row-NVDA")).toBeVisible();
    await expect.poll(() => readCash(page)).toBeLessThan(cashBefore);
  });

  test("defaults a trade to AAPL when the message names no ticker", async ({
    page,
  }) => {
    await openTerminal(page);
    await send(page, "buy something for me");

    await expect(lastReply(page).getByTestId("chat-action-trade")).toContainText(
      /buy 1 AAPL/i,
    );
    await expect(page.getByTestId("positions-row-AAPL")).toBeVisible();
  });

  test("executes a sell through chat", async ({ page }) => {
    await openTerminal(page);
    await page.getByTestId("trade-ticker").fill("AMZN");
    await page.getByTestId("trade-quantity").fill("2");
    await page.getByTestId("trade-buy").click();
    await expect(page.getByTestId("positions-row-AMZN")).toContainText("2");

    await send(page, "sell AMZN");

    await expect(lastReply(page).getByTestId("chat-action-trade")).toContainText(
      /sell 1 AMZN/i,
    );
    await expect(page.getByTestId("positions-row-AMZN")).toContainText("1");
  });

  test("adds a watchlist ticker through chat", async ({ page }) => {
    await openTerminal(page);
    await expect(page.getByTestId("watchlist-row-PYPL")).toBeHidden();

    await send(page, "add PYPL to the watchlist");

    await expect(
      lastReply(page).getByTestId("chat-action-watchlist"),
    ).toContainText("+PYPL");
    await expect(page.getByTestId("watchlist-row-PYPL")).toBeVisible();
  });

  test("removes a watchlist ticker through chat", async ({ page }) => {
    await openTerminal(page);

    await send(page, "watch PYPL");
    await expect(page.getByTestId("watchlist-row-PYPL")).toBeVisible();

    await send(page, "remove PYPL");

    await expect(
      lastReply(page).getByTestId("chat-action-watchlist"),
    ).toContainText("-PYPL");
    await expect(page.getByTestId("watchlist-row-PYPL")).toBeHidden();
  });

  test("the conversation survives a page reload", async ({ page }) => {
    await openTerminal(page);
    await send(page, "buy TSLA now");

    const messages = page.getByTestId("chat-message");
    const total = await messages.count();

    await page.reload();
    await expect(page.getByTestId("watchlist-row-AAPL")).toBeVisible();

    await expect(messages).toHaveCount(total);
    await expect(messages.nth(total - 2)).toContainText("buy TSLA now");
    await expect(messages.nth(total - 2)).toHaveAttribute("data-role", "user");
    await expect(messages.last()).toContainText(/TSLA/);

    // Executed actions are stored alongside the message, so the inline
    // confirmation comes back with it rather than being lost on reload.
    await expect(messages.last().getByTestId("chat-action-trade")).toContainText(
      /buy 1 TSLA/i,
    );
  });
});
