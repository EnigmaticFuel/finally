import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Heatmap } from "@/components/Heatmap";
import { MainChart } from "@/components/MainChart";
import { PnlChart } from "@/components/PnlChart";
import { Sparkline } from "@/components/Sparkline";
import { livePositions } from "@/lib/derive";
import { priceMap, quote, sampleSnapshots, samplePortfolio } from "./fakes";

const points = Array.from({ length: 60 }, (_, i) => 190 + i * 0.05);

describe("Sparkline", () => {
  it("draws a line from the seeded history", () => {
    render(<Sparkline points={points} positive testId="spark" />);
    expect(screen.getByTestId("spark").querySelector("path")).toBeTruthy();
  });

  it("degrades to a flat rule rather than an empty box with one point", () => {
    render(<Sparkline points={[190]} positive testId="spark" />);
    expect(screen.getByTestId("spark").querySelector("path")).toBeNull();
    expect(screen.getByTestId("spark")).toBeInTheDocument();
  });
});

describe("MainChart", () => {
  it("renders the selected ticker and its live quote", () => {
    render(
      <MainChart
        ticker="AAPL"
        points={points}
        quote={quote("AAPL", 192.5, 1.75)}
      />,
    );
    expect(screen.getByText(/AAPL/)).toBeInTheDocument();
    expect(screen.getByText(/192\.50 \+1\.75%/)).toBeInTheDocument();
    expect(screen.getByTestId("main-chart").querySelector("svg")).toBeTruthy();
  });

  it("prompts for a selection when nothing is chosen", () => {
    render(<MainChart ticker={null} points={[]} />);
    expect(screen.getByTestId("main-chart")).toHaveTextContent(
      "SELECT A TICKER",
    );
  });
});

describe("PnlChart", () => {
  it("plots the snapshots plus the live total", () => {
    render(<PnlChart snapshots={sampleSnapshots} liveValue={10200} />);
    expect(screen.getByTestId("pnl-chart").querySelector("svg")).toBeTruthy();
  });

  it("shows a percentage change from the first snapshot to the live value", () => {
    render(<PnlChart snapshots={sampleSnapshots} liveValue={10500} />);
    expect(screen.getByText("+5.00%")).toBeInTheDocument();
  });

  it("waits rather than crashing with no snapshots", () => {
    render(<PnlChart snapshots={[]} liveValue={0} />);
    expect(screen.getByTestId("pnl-chart")).toHaveTextContent(
      "AWAITING SNAPSHOTS",
    );
  });
});

describe("Heatmap", () => {
  it("draws a cell per position", () => {
    const positions = livePositions(
      samplePortfolio.positions,
      priceMap(quote("AAPL", 200)),
    );
    render(<Heatmap positions={positions} />);
    expect(screen.getByTestId("heatmap").querySelector("rect")).toBeTruthy();
  });

  it("draws no cell for the tree root", () => {
    const positions = livePositions(
      samplePortfolio.positions,
      priceMap(quote("AAPL", 200)),
    );
    render(<Heatmap positions={positions} />);
    expect(screen.getByTestId("heatmap").querySelectorAll("rect")).toHaveLength(
      positions.length,
    );
  });

  it("shows an empty state with no positions", () => {
    render(<Heatmap positions={[]} />);
    expect(screen.getByTestId("heatmap")).toHaveTextContent("NO POSITIONS");
  });
});
