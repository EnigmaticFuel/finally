"use client";

import { Panel } from "./Panel";
import { PriceCell } from "./PriceCell";
import { money, percent, quantity, signedMoney, toneClass } from "@/lib/format";
import type { LivePosition } from "@/lib/derive";

const COLUMNS = [
  "Symbol",
  "Qty",
  "Avg Cost",
  "Last",
  "Mkt Value",
  "Unrealized",
  "Chg %",
];

export function PositionsTable({
  positions,
  onSelect,
}: {
  positions: LivePosition[];
  onSelect: (ticker: string) => void;
}) {
  return (
    <Panel
      label="positions"
      accent="gold"
      meta={`${positions.length}`}
      className="h-full"
      bodyClassName="overflow-y-auto"
    >
      {positions.length === 0 ? (
        <p
          data-testid="positions-empty"
          className="px-2 py-6 text-center text-[11px] tracking-[0.14em] text-dim"
        >
          NO OPEN POSITIONS
        </p>
      ) : (
        <table className="w-full text-[12px]">
          <thead className="sticky top-0 bg-panel">
            <tr className="border-b border-line text-[9px] tracking-[0.14em] text-dim uppercase">
              {COLUMNS.map((column, index) => (
                <th
                  key={column}
                  className={`px-3 py-1.5 font-medium ${
                    index === 0 ? "text-left" : "text-right"
                  }`}
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {positions.map((position) => (
              <tr
                key={position.ticker}
                data-testid={`positions-row-${position.ticker}`}
                onClick={() => onSelect(position.ticker)}
                className="cursor-pointer border-b border-line/60 hover:bg-raise"
              >
                <td className="px-3 py-1.5 tracking-wide">{position.ticker}</td>
                <td className="px-3 py-1.5 text-right text-muted">
                  {quantity(position.quantity)}
                </td>
                <td className="px-3 py-1.5 text-right text-muted">
                  {money(position.avg_cost)}
                </td>
                <td className="px-3 py-1.5 text-right">
                  <PriceCell
                    value={position.live_price}
                    testId={`position-price-${position.ticker}`}
                  />
                </td>
                <td className="px-3 py-1.5 text-right">
                  {money(position.live_market_value)}
                </td>
                <td
                  data-testid={`position-pnl-${position.ticker}`}
                  className={`px-3 py-1.5 text-right ${toneClass(position.live_pnl)}`}
                >
                  {signedMoney(position.live_pnl)}
                </td>
                <td
                  className={`px-3 py-1.5 text-right ${toneClass(position.live_pnl_percent)}`}
                >
                  {percent(position.live_pnl_percent)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}
