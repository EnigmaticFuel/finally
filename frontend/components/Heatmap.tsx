"use client";

import { ResponsiveContainer, Treemap } from "recharts";
import { Panel } from "./Panel";
import { money, percent } from "@/lib/format";
import type { LivePosition } from "@/lib/derive";

/** Saturation carries magnitude, hue carries direction. Four percent of move
    reaches full saturation, which is roughly a strong day for a single name. */
function cellColor(pnlPercent: number): string {
  const weight = Math.min(Math.abs(pnlPercent) / 4, 1);
  const channel = pnlPercent >= 0 ? "38,194,129" : "240,69,75";
  return `rgba(${channel},${(0.12 + 0.5 * weight).toFixed(3)})`;
}

interface CellProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  depth?: number;
  name?: string;
  pnlPercent?: number;
}

function HeatCell(props: CellProps) {
  const { x = 0, y = 0, width = 0, height = 0, name = "", pnlPercent = 0 } = props;
  // Recharts renders the tree root through this same component. It has no
  // position behind it, so drawing it would paint the whole panel.
  if (props.depth === 0) return null;
  if (width <= 0 || height <= 0) return null;

  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        fill={cellColor(pnlPercent)}
        stroke="#0d1117"
        strokeWidth={1}
      />
      {width > 44 && height > 24 ? (
        <text
          x={x + 6}
          y={y + 16}
          fill="#dbe3ee"
          fontSize={11}
          fontFamily="ui-monospace, monospace"
        >
          {name}
        </text>
      ) : null}
      {width > 60 && height > 40 ? (
        <text
          x={x + 6}
          y={y + 30}
          fill={pnlPercent >= 0 ? "#26c281" : "#f0454b"}
          fontSize={10}
          fontFamily="ui-monospace, monospace"
        >
          {percent(pnlPercent)}
        </text>
      ) : null}
    </g>
  );
}

export function Heatmap({ positions }: { positions: LivePosition[] }) {
  const data = positions.map((position) => ({
    name: position.ticker,
    size: Math.max(position.live_market_value, 0.01),
    pnlPercent: position.live_pnl_percent,
  }));
  const invested = positions.reduce((sum, p) => sum + p.live_market_value, 0);

  return (
    <Panel
      label="allocation"
      accent="gold"
      meta={positions.length ? money(invested) : null}
      className="min-w-0 flex-1"
      bodyClassName="p-1"
    >
      <div data-testid="heatmap" className="h-full w-full">
        {data.length === 0 ? (
          <div className="flex h-full items-center justify-center text-[11px] tracking-[0.16em] text-dim">
            NO POSITIONS
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <Treemap
              data={data}
              dataKey="size"
              stroke="#0d1117"
              content={<HeatCell />}
              isAnimationActive={false}
            />
          </ResponsiveContainer>
        )}
      </div>
    </Panel>
  );
}
