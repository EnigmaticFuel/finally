import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Watchlist } from "@/components/Watchlist";
import type { PriceMap } from "@/lib/types";
import { priceMap, quote, watchlistTicker } from "./fakes";

const entries = [
  watchlistTicker("AAPL", 190.5, 0.687),
  watchlistTicker("TSLA", 240, -1.25),
];

function renderWatchlist(
  overrides: Partial<Parameters<typeof Watchlist>[0]> = {},
  prices: PriceMap = {},
) {
  const props = {
    entries,
    prices,
    series: {},
    selected: null,
    error: null,
    onSelect: vi.fn(),
    onAdd: vi.fn(),
    onRemove: vi.fn(),
    ...overrides,
  };
  render(<Watchlist {...props} />);
  return props;
}

describe("Watchlist", () => {
  it("renders a row per ticker with its seeded price", () => {
    renderWatchlist();
    expect(screen.getByTestId("watchlist-row-AAPL")).toBeInTheDocument();
    expect(screen.getByTestId("watchlist-price-AAPL")).toHaveTextContent(
      "190.50",
    );
    expect(screen.getByTestId("watchlist-price-TSLA")).toHaveTextContent(
      "240.00",
    );
  });

  it("shows change since the session open, not the tick-over-tick move", () => {
    renderWatchlist();
    expect(screen.getByTestId("watchlist-change-AAPL")).toHaveTextContent(
      "+0.69%",
    );
    expect(screen.getByTestId("watchlist-change-TSLA")).toHaveTextContent(
      "-1.25%",
    );
  });

  it("prefers the streamed quote over the seeded row", () => {
    renderWatchlist({}, priceMap(quote("AAPL", 195.25, 3.1)));
    expect(screen.getByTestId("watchlist-price-AAPL")).toHaveTextContent(
      "195.25",
    );
    expect(screen.getByTestId("watchlist-change-AAPL")).toHaveTextContent(
      "+3.10%",
    );
  });

  it("paints a sparkline from the seeded history on first paint", () => {
    renderWatchlist();
    const spark = screen.getByTestId("sparkline-AAPL");
    expect(spark.querySelector("path")).toBeTruthy();
  });

  it("selects a ticker when its row is clicked", async () => {
    const props = renderWatchlist();
    await userEvent.click(screen.getByTestId("watchlist-row-TSLA"));
    expect(props.onSelect).toHaveBeenCalledWith("TSLA");
  });

  it("adds an uppercased ticker and clears the input", async () => {
    const props = renderWatchlist();
    const input = screen.getByTestId("watchlist-add-input");
    await userEvent.type(input, "pypl");
    await userEvent.click(screen.getByTestId("watchlist-add-button"));

    expect(props.onAdd).toHaveBeenCalledWith("PYPL");
    expect(input).toHaveValue("");
  });

  it("ignores an empty add", async () => {
    const props = renderWatchlist();
    await userEvent.click(screen.getByTestId("watchlist-add-button"));
    expect(props.onAdd).not.toHaveBeenCalled();
  });

  it("removes a ticker without also selecting the row", async () => {
    const props = renderWatchlist();
    await userEvent.click(screen.getByTestId("watchlist-remove-AAPL"));
    expect(props.onRemove).toHaveBeenCalledWith("AAPL");
    expect(props.onSelect).not.toHaveBeenCalled();
  });

  it("shows the server's rejection message verbatim", () => {
    renderWatchlist({ error: "Cannot remove AAPL while a position is held" });
    expect(screen.getByTestId("watchlist-error")).toHaveTextContent(
      "Cannot remove AAPL while a position is held",
    );
  });

  it("renders an empty state rather than crashing when the fetch failed", () => {
    renderWatchlist({ entries: [] });
    expect(screen.getByTestId("watchlist-empty")).toBeInTheDocument();
  });
});
