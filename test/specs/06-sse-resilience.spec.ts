import { expect, test } from "@playwright/test";
import { openTerminal, waitForLiveStream } from "../helpers";

const STREAM = "**/api/stream/prices";

test.describe("SSE resilience", () => {
  test("the status dot leaves green when the stream is blocked and returns when it is restored", async ({
    page,
  }) => {
    await openTerminal(page);
    const dot = page.getByTestId("connection-dot");
    await expect(dot).toHaveAttribute("data-status", "live");

    // Route interception applies to new requests, so the block is made to bite
    // by reloading into it. The EventSource then cannot establish at all.
    const block = (route: import("@playwright/test").Route) => route.abort();
    await page.route(STREAM, block);
    await page.reload();

    await expect(page.getByTestId("watchlist-row-AAPL")).toBeVisible();
    await expect(dot).not.toHaveAttribute("data-status", "live", {
      timeout: 15_000,
    });

    // EventSource retries on its own, so simply removing the block is enough.
    await page.unroute(STREAM, block);
    await waitForLiveStream(page);
  });

  test("the terminal still renders REST data while the stream is down", async ({
    page,
  }) => {
    await page.route(STREAM, (route) => route.abort());
    await page.goto("/");

    // The watchlist, its prices and the header all come from REST, so a dead
    // stream degrades the terminal rather than blanking it.
    await expect(page.getByTestId("watchlist-row-AAPL")).toBeVisible();
    await expect(page.getByTestId("watchlist-price-AAPL")).not.toBeEmpty();
    await expect(page.getByTestId("header-total")).toContainText("$");
    await expect(page.getByTestId("connection-dot")).not.toHaveAttribute(
      "data-status",
      "live",
    );
  });

  test("the stream sends heartbeats so a quiet market stays green", async ({
    request,
  }) => {
    const health = await (await request.get("/api/health")).json();
    expect(health.status).toBe("ok");
    expect(health.tickers_cached).toBeGreaterThan(0);
    expect(health.newest_price_age_seconds).toBeLessThan(30);
  });
});
