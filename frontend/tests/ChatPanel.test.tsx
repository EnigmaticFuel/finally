import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChatPanel } from "@/components/ChatPanel";
import { sampleMessages } from "./fakes";

function renderPanel(
  overrides: Partial<Parameters<typeof ChatPanel>[0]> = {},
) {
  const props = {
    messages: sampleMessages,
    loading: false,
    collapsed: false,
    onToggle: vi.fn(),
    onSend: vi.fn(),
    ...overrides,
  };
  render(<ChatPanel {...props} />);
  return props;
}

describe("ChatPanel", () => {
  it("renders the conversation in order with roles", () => {
    renderPanel();
    const rendered = screen.getAllByTestId("chat-message");
    expect(rendered).toHaveLength(2);
    expect(rendered[0]).toHaveAttribute("data-role", "user");
    expect(rendered[0]).toHaveTextContent("buy 1 AAPL");
    expect(rendered[1]).toHaveAttribute("data-role", "assistant");
    expect(rendered[1]).toHaveTextContent("Bought 1 share of AAPL.");
  });

  it("shows executed trades inline as confirmations", () => {
    renderPanel();
    expect(screen.getByTestId("chat-action-trade")).toHaveTextContent(
      "buy 1 AAPL",
    );
  });

  it("shows watchlist changes inline", () => {
    renderPanel({
      messages: [
        {
          role: "assistant",
          content: "Added PYPL.",
          actions: {
            trades: [],
            watchlist_changes: [{ ticker: "PYPL", action: "add" }],
          },
          created_at: "2026-07-25T14:03:00Z",
        },
      ],
    });
    expect(screen.getByTestId("chat-action-watchlist")).toHaveTextContent(
      "+PYPL",
    );
  });

  it("renders no action chips for a plain reply", () => {
    renderPanel({
      messages: [
        {
          role: "assistant",
          content: "You are holding 1 position.",
          actions: { trades: [], watchlist_changes: [] },
          created_at: "2026-07-25T14:03:00Z",
        },
      ],
    });
    expect(screen.queryByTestId("chat-action-trade")).toBeNull();
  });

  it("shows a loading indicator while the assistant is thinking", () => {
    renderPanel({ loading: true });
    expect(screen.getByTestId("chat-loading")).toBeInTheDocument();
  });

  it("hides the loading indicator when idle", () => {
    renderPanel();
    expect(screen.queryByTestId("chat-loading")).toBeNull();
  });

  it("sends a trimmed message and clears the input", async () => {
    const props = renderPanel({ messages: [] });
    const input = screen.getByTestId("chat-input");
    await userEvent.type(input, "  how am I doing?  ");
    await userEvent.click(screen.getByTestId("chat-send"));

    expect(props.onSend).toHaveBeenCalledWith("how am I doing?");
    expect(input).toHaveValue("");
  });

  it("refuses to send while a response is in flight", async () => {
    const props = renderPanel({ loading: true });
    await userEvent.type(screen.getByTestId("chat-input"), "hello{enter}");
    expect(props.onSend).not.toHaveBeenCalled();
  });

  it("collapses to a rail that can be reopened", async () => {
    const props = renderPanel({ collapsed: true });
    expect(screen.queryByTestId("chat-input")).toBeNull();
    await userEvent.click(screen.getByTestId("chat-toggle"));
    expect(props.onToggle).toHaveBeenCalled();
  });
});
