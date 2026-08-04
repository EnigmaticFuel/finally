import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

/** jsdom has no EventSource. Tests that care about the stream install
    FakeEventSource from ./fakes; everything else just needs it to exist. */
import { FakeEventSource } from "./fakes";

globalThis.EventSource = FakeEventSource as unknown as typeof EventSource;

/** Recharts measures its container, which jsdom reports as 0x0. Without a size
    ResponsiveContainer renders nothing and no chart assertion can pass. */
const BOX = { width: 640, height: 320 };

class ResizeObserverStub {
  constructor(private readonly callback: ResizeObserverCallback) {}

  observe(target: Element) {
    this.callback(
      [{ target, contentRect: BOX }] as unknown as ResizeObserverEntry[],
      this as unknown as ResizeObserver,
    );
  }

  unobserve() {}
  disconnect() {}
}

const RECT = {
  ...BOX,
  top: 0,
  left: 0,
  right: BOX.width,
  bottom: BOX.height,
  x: 0,
  y: 0,
} as DOMRect;

HTMLElement.prototype.getBoundingClientRect = () => RECT;

globalThis.ResizeObserver =
  ResizeObserverStub as unknown as typeof ResizeObserver;

for (const [property, value] of [
  ["offsetWidth", 640],
  ["offsetHeight", 320],
  ["clientWidth", 640],
  ["clientHeight", 320],
] as const) {
  Object.defineProperty(HTMLElement.prototype, property, {
    configurable: true,
    value,
  });
}

afterEach(() => {
  cleanup();
  FakeEventSource.instances = [];
  vi.restoreAllMocks();
});
