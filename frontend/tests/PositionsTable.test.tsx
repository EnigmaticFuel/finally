import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { PositionsTable } from "@/components/PositionsTable";
import { livePositions } from "@/lib/derive";
import { priceMap, quote, samplePortfolio } from "./fakes";

/** AAPL: 10 shares at 188.60, streaming at 200.00. */
const positions = livePositions(
  samplePortfolio.positions,
  priceMap(quote("AAPL", 200)),
);

describe("PositionsTable", () => {
  it("renders a row per position", () => {
    render(<PositionsTable positions={positions} onSelect={vi.fn()} />);
    expect(screen.getByTestId("positions-row-AAPL")).toBeInTheDocument();
  });

  it("shows the live price, not the price the server last quoted", () => {
    render(<PositionsTable positions={positions} onSelect={vi.fn()} />);
    expect(screen.getByTestId("position-price-AAPL")).toHaveTextContent(
      "200.00",
    );
  });

  it("computes unrealized P&L from the live price", () => {
    render(<PositionsTable positions={positions} onSelect={vi.fn()} />);
    const pnl = screen.getByTestId("position-pnl-AAPL");
    expect(pnl).toHaveTextContent("+$114.00");
    expect(pnl).toHaveClass("text-up");
  });

  it("tones a losing position red", () => {
    const losing = livePositions(
      samplePortfolio.positions,
      priceMap(quote("AAPL", 150)),
    );
    render(<PositionsTable positions={losing} onSelect={vi.fn()} />);
    expect(screen.getByTestId("position-pnl-AAPL")).toHaveClass("text-down");
  });

  it("selects a ticker when its row is clicked", async () => {
    const onSelect = vi.fn();
    render(<PositionsTable positions={positions} onSelect={onSelect} />);
    await userEvent.click(screen.getByTestId("positions-row-AAPL"));
    expect(onSelect).toHaveBeenCalledWith("AAPL");
  });

  it("shows an empty state with no positions", () => {
    render(<PositionsTable positions={[]} onSelect={vi.fn()} />);
    expect(screen.getByTestId("positions-empty")).toBeInTheDocument();
  });
});
