import { describe, expect, it } from "vitest";
import {
  clockTime,
  money,
  percent,
  price,
  quantity,
  signedMoney,
  toneClass,
} from "@/lib/format";

describe("format", () => {
  it("renders money with two decimals and a thousands separator", () => {
    expect(money(10120.75)).toBe("$10,120.75");
    expect(money(-5)).toBe("-$5.00");
  });

  it("signs money explicitly so a gain is never ambiguous", () => {
    expect(signedMoney(19)).toBe("+$19.00");
    expect(signedMoney(-19)).toBe("-$19.00");
  });

  it("signs percentages and keeps two decimals", () => {
    expect(percent(0.687)).toBe("+0.69%");
    expect(percent(-1.5)).toBe("-1.50%");
    expect(percent(0)).toBe("+0.00%");
  });

  it("prices to two decimals without a currency symbol", () => {
    expect(price(190.5)).toBe("190.50");
  });

  it("shows whole share counts without decimals", () => {
    expect(quantity(10)).toBe("10");
    expect(quantity(1.5)).toBe("1.5000");
  });

  it("tones green above zero, red below, muted at zero", () => {
    expect(toneClass(1)).toBe("text-up");
    expect(toneClass(-1)).toBe("text-down");
    expect(toneClass(0)).toBe("text-muted");
  });

  it("ignores an unparseable timestamp", () => {
    expect(clockTime("not a date")).toBe("");
  });
});
