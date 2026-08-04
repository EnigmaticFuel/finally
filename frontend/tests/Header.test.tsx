import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Header } from "@/components/Header";
import type { ConnectionStatus } from "@/lib/types";

function renderHeader(status: ConnectionStatus = "live") {
  render(
    <Header
      cash={8234.5}
      totalValue={10139.5}
      unrealizedPnl={19}
      status={status}
    />,
  );
}

describe("Header", () => {
  it("shows cash and the live total value", () => {
    renderHeader();
    expect(screen.getByTestId("header-cash")).toHaveTextContent("$8,234.50");
    expect(screen.getByTestId("header-total")).toHaveTextContent("$10,139.50");
  });

  it("signs and tones unrealized P&L", () => {
    renderHeader();
    const unrealized = screen.getByTestId("header-unrealized");
    expect(unrealized).toHaveTextContent("+$19.00");
    expect(unrealized).toHaveClass("text-up");
  });

  it("tones a loss red", () => {
    render(
      <Header cash={100} totalValue={150} unrealizedPnl={-25} status="live" />,
    );
    expect(screen.getByTestId("header-unrealized")).toHaveClass("text-down");
  });

  it("colors the connection dot green when the stream is live", () => {
    renderHeader("live");
    const dot = screen.getByTestId("connection-dot");
    expect(dot).toHaveAttribute("data-status", "live");
    expect(dot).toHaveClass("bg-up");
  });

  it("colors the dot yellow while degraded", () => {
    renderHeader("degraded");
    expect(screen.getByTestId("connection-dot")).toHaveClass("bg-gold");
  });

  it("colors the dot red when the stream is closed", () => {
    renderHeader("down");
    expect(screen.getByTestId("connection-dot")).toHaveClass("bg-down");
  });
});
