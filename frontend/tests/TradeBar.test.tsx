import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { TradeBar } from "@/components/TradeBar";
import type { TradeFill } from "@/lib/types";

const fill: TradeFill = {
  ticker: "AAPL",
  side: "buy",
  quantity: 10,
  fill_price: 190.52,
  total_cost: 1905.2,
  cash_balance: 8234.5,
  executed_at: "2026-07-25T14:03:11Z",
};

describe("TradeBar", () => {
  it("prefills the symbol from the selected ticker", () => {
    render(<TradeBar selected="TSLA" onSubmit={vi.fn()} />);
    expect(screen.getByTestId("trade-ticker")).toHaveValue("TSLA");
  });

  it("submits a buy and reports the fill price the server returned", async () => {
    const onSubmit = vi.fn().mockResolvedValue(fill);
    render(<TradeBar selected="AAPL" onSubmit={onSubmit} />);

    await userEvent.type(screen.getByTestId("trade-quantity"), "10");
    await userEvent.click(screen.getByTestId("trade-buy"));

    expect(onSubmit).toHaveBeenCalledWith("AAPL", 10, "buy");
    const status = screen.getByTestId("trade-status");
    expect(status).toHaveTextContent("FILLED BUY");
    expect(status).toHaveTextContent("190.52");
    expect(status).toHaveTextContent("$1,905.20");
  });

  it("submits a sell", async () => {
    const onSubmit = vi.fn().mockResolvedValue({ ...fill, side: "sell" });
    render(<TradeBar selected="AAPL" onSubmit={onSubmit} />);

    await userEvent.type(screen.getByTestId("trade-quantity"), "2.5");
    await userEvent.click(screen.getByTestId("trade-sell"));

    expect(onSubmit).toHaveBeenCalledWith("AAPL", 2.5, "sell");
    expect(screen.getByTestId("trade-status")).toHaveTextContent("FILLED SELL");
  });

  it("uppercases a hand-typed symbol", async () => {
    const onSubmit = vi.fn().mockResolvedValue(fill);
    render(<TradeBar selected={null} onSubmit={onSubmit} />);

    await userEvent.type(screen.getByTestId("trade-ticker"), "nvda");
    await userEvent.type(screen.getByTestId("trade-quantity"), "1");
    await userEvent.click(screen.getByTestId("trade-buy"));

    expect(onSubmit).toHaveBeenCalledWith("NVDA", 1, "buy");
  });

  it("rejects a non-positive quantity without calling the server", async () => {
    const onSubmit = vi.fn();
    render(<TradeBar selected="AAPL" onSubmit={onSubmit} />);

    await userEvent.type(screen.getByTestId("trade-quantity"), "0");
    await userEvent.click(screen.getByTestId("trade-buy"));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByTestId("trade-status")).toHaveTextContent(
      "quantity above zero",
    );
  });

  it("shows the server's rejection message verbatim", async () => {
    const onSubmit = vi
      .fn()
      .mockRejectedValue(
        new Error("Insufficient cash: need $1905.20, have $800.00"),
      );
    render(<TradeBar selected="AAPL" onSubmit={onSubmit} />);

    await userEvent.type(screen.getByTestId("trade-quantity"), "10");
    await userEvent.click(screen.getByTestId("trade-buy"));

    expect(screen.getByTestId("trade-status")).toHaveTextContent(
      "Insufficient cash: need $1905.20, have $800.00",
    );
  });

  it("clears the quantity after a fill", async () => {
    const onSubmit = vi.fn().mockResolvedValue(fill);
    render(<TradeBar selected="AAPL" onSubmit={onSubmit} />);

    await userEvent.type(screen.getByTestId("trade-quantity"), "10");
    await userEvent.click(screen.getByTestId("trade-buy"));

    expect(screen.getByTestId("trade-quantity")).toHaveValue("");
  });
});
