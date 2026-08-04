import { render, screen } from "@testing-library/react";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PriceCell } from "@/components/PriceCell";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

function cell() {
  return screen.getByTestId("last");
}

describe("PriceCell", () => {
  it("renders the price to two decimals", () => {
    render(<PriceCell value={190.5} testId="last" />);
    expect(cell()).toHaveTextContent("190.50");
  });

  it("does not flash on first paint", () => {
    render(<PriceCell value={190.5} testId="last" />);
    expect(cell().className).not.toContain("flash");
  });

  it("flashes green on an uptick", () => {
    const view = render(<PriceCell value={190.5} testId="last" />);
    view.rerender(<PriceCell value={191} testId="last" />);
    expect(cell()).toHaveClass("flash-up");
  });

  it("flashes red on a downtick", () => {
    const view = render(<PriceCell value={190.5} testId="last" />);
    view.rerender(<PriceCell value={190} testId="last" />);
    expect(cell()).toHaveClass("flash-down");
  });

  it("does not flash when the price is unchanged", () => {
    const view = render(<PriceCell value={190.5} testId="last" />);
    view.rerender(<PriceCell value={190.5} testId="last" />);
    expect(cell().className).not.toContain("flash");
  });

  it("clears the flash after 500ms", () => {
    const view = render(<PriceCell value={190.5} testId="last" />);
    view.rerender(<PriceCell value={191} testId="last" />);
    expect(cell()).toHaveClass("flash-up");

    act(() => void vi.advanceTimersByTime(500));
    expect(cell().className).not.toContain("flash");
    expect(cell()).toHaveTextContent("191.00");
  });

  it("re-triggers on a second uptick in a row", () => {
    const view = render(<PriceCell value={190.5} testId="last" />);
    view.rerender(<PriceCell value={191} testId="last" />);
    const first = cell();

    view.rerender(<PriceCell value={191.5} testId="last" />);
    expect(cell()).toHaveClass("flash-up");
    expect(cell()).not.toBe(first);
  });
});
