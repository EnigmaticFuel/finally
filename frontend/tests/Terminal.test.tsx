import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Terminal from "@/app/page";
import {
  FakeEventSource,
  callCount,
  failWith,
  mockFetch,
  priceMap,
  quote,
  sampleSnapshots,
  samplePortfolio,
  watchlistTicker,
} from "./fakes";

const watchlist = {
  tickers: [
    watchlistTicker("AAPL", 190.5, 0.687),
    watchlistTicker("TSLA", 240, -1.25),
  ],
};

/** GET returns stored history, POST returns a reply. Both live at /api/chat. */
function chatRoute(reply: unknown, history: unknown[] = []) {
  return (init?: RequestInit) =>
    init?.method === "POST" ? reply : { messages: history };
}

function install(overrides: Record<string, unknown> = {}) {
  const fetchMock = mockFetch({
    "/api/portfolio/history": { snapshots: sampleSnapshots },
    "/api/portfolio/trade": {
      ticker: "AAPL",
      side: "buy",
      quantity: 1,
      fill_price: 190.52,
      total_cost: 190.52,
      cash_balance: 8043.98,
      executed_at: "2026-07-25T14:03:11Z",
    },
    "/api/portfolio": samplePortfolio,
    "/api/watchlist": watchlist,
    "/api/chat": chatRoute({
      message: "Nothing to do.",
      trades: [],
      watchlist_changes: [],
    }),
    ...overrides,
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** Wait for the first paint driven by the mocked endpoints. */
async function loaded() {
  await waitFor(() =>
    expect(screen.getByTestId("watchlist-row-AAPL")).toBeInTheDocument(),
  );
}

beforeEach(() => {
  vi.unstubAllGlobals();
});

describe("Terminal", () => {
  it("renders the watchlist, positions and header from the server state", async () => {
    install();
    render(<Terminal />);
    await loaded();

    expect(screen.getByTestId("watchlist-row-TSLA")).toBeInTheDocument();
    expect(screen.getByTestId("positions-row-AAPL")).toBeInTheDocument();
    expect(screen.getByTestId("header-cash")).toHaveTextContent("$8,234.50");
  });

  it("recomputes the total from the price stream, not from the server total", async () => {
    install();
    render(<Terminal />);
    await loaded();

    FakeEventSource.last.open();
    FakeEventSource.last.emit(priceMap(quote("AAPL", 200), quote("TSLA", 250)));

    // 8234.50 cash + 10 AAPL at 200.00
    await waitFor(() =>
      expect(screen.getByTestId("header-total")).toHaveTextContent(
        "$10,234.50",
      ),
    );
    expect(screen.getByTestId("position-price-AAPL")).toHaveTextContent(
      "200.00",
    );
    expect(screen.getByTestId("watchlist-price-TSLA")).toHaveTextContent(
      "250.00",
    );
  });

  it("drives the connection dot from the stream", async () => {
    install();
    render(<Terminal />);
    await loaded();

    expect(screen.getByTestId("connection-dot")).toHaveAttribute(
      "data-status",
      "degraded",
    );

    FakeEventSource.last.open();
    await waitFor(() =>
      expect(screen.getByTestId("connection-dot")).toHaveAttribute(
        "data-status",
        "live",
      ),
    );

    FakeEventSource.last.fail(FakeEventSource.CLOSED);
    await waitFor(() =>
      expect(screen.getByTestId("connection-dot")).toHaveAttribute(
        "data-status",
        "down",
      ),
    );
  });

  it("refetches portfolio and watchlist after a manual trade", async () => {
    const fetchMock = install();
    render(<Terminal />);
    await loaded();

    const before = {
      portfolio: callCount(fetchMock, "/api/portfolio"),
      watchlist: callCount(fetchMock, "/api/watchlist"),
    };

    await userEvent.type(screen.getByTestId("trade-quantity"), "1");
    await userEvent.click(screen.getByTestId("trade-buy"));

    await waitFor(() =>
      expect(callCount(fetchMock, "/api/portfolio")).toBe(before.portfolio + 1),
    );
    expect(callCount(fetchMock, "/api/watchlist")).toBe(before.watchlist + 1);
    expect(screen.getByTestId("trade-status")).toHaveTextContent("190.52");
  });

  it("refetches after a chat response that changed server state", async () => {
    const fetchMock = install({
      "/api/chat": chatRoute({
        message: "Bought 1 AAPL.",
        trades: [{ ticker: "AAPL", side: "buy", quantity: 1 }],
        watchlist_changes: [],
      }),
    });
    render(<Terminal />);
    await loaded();
    const before = callCount(fetchMock, "/api/portfolio");

    await userEvent.type(screen.getByTestId("chat-input"), "buy 1 AAPL");
    await userEvent.click(screen.getByTestId("chat-send"));

    await waitFor(() =>
      expect(screen.getByTestId("chat-action-trade")).toHaveTextContent(
        "buy 1 AAPL",
      ),
    );
    expect(callCount(fetchMock, "/api/portfolio")).toBe(before + 1);
  });

  it("does not refetch after a chat response with no actions", async () => {
    const fetchMock = install({
      "/api/chat": chatRoute({
        message: "You hold 1 position.",
        trades: [],
        watchlist_changes: [],
      }),
    });
    render(<Terminal />);
    await loaded();
    const before = callCount(fetchMock, "/api/portfolio");

    await userEvent.type(screen.getByTestId("chat-input"), "how am I doing?");
    await userEvent.click(screen.getByTestId("chat-send"));

    await waitFor(() =>
      expect(screen.getByText("You hold 1 position.")).toBeInTheDocument(),
    );
    expect(callCount(fetchMock, "/api/portfolio")).toBe(before);
  });

  it("repopulates the chat panel from stored history on load", async () => {
    install({
      "/api/chat": chatRoute({}, [
        {
          role: "user",
          content: "what do I own?",
          actions: null,
          created_at: "2026-07-25T14:02:00Z",
        },
      ]),
    });
    render(<Terminal />);

    await waitFor(() =>
      expect(screen.getByText("what do I own?")).toBeInTheDocument(),
    );
  });

  it("adds a ticker and reloads the watchlist", async () => {
    const fetchMock = install();
    render(<Terminal />);
    await loaded();
    const before = callCount(fetchMock, "/api/watchlist");

    await userEvent.type(screen.getByTestId("watchlist-add-input"), "pypl");
    await userEvent.click(screen.getByTestId("watchlist-add-button"));

    await waitFor(() =>
      expect(callCount(fetchMock, "/api/watchlist")).toBe(before + 1),
    );
    const post = fetchMock.mock.calls.find(
      (call) => call[1]?.method === "POST" && call[0] === "/api/watchlist",
    );
    expect(post?.[1]?.body).toBe(JSON.stringify({ ticker: "PYPL" }));
  });

  it("surfaces a rejected removal instead of silently failing", async () => {
    install({
      "/api/watchlist/AAPL": failWith(
        409,
        "Cannot remove AAPL while a position is held",
      ),
    });
    render(<Terminal />);
    await loaded();

    await userEvent.click(screen.getByTestId("watchlist-remove-AAPL"));
    await waitFor(() =>
      expect(screen.getByTestId("watchlist-error")).toHaveTextContent(
        "Cannot remove AAPL while a position is held",
      ),
    );
  });

  it("renders empty panels rather than crashing when every fetch fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("backend not up yet");
      }),
    );
    render(<Terminal />);

    await waitFor(() =>
      expect(screen.getByTestId("watchlist-empty")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("positions-empty")).toBeInTheDocument();
    expect(screen.getByTestId("header-total")).toHaveTextContent("$0.00");
  });
});
