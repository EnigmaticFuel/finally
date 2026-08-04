"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  YAxis,
} from "recharts";
import { Panel } from "./Panel";
import { money, percent } from "@/lib/format";
import type { Snapshot } from "@/lib/types";

function PnlTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { value: number }[];
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="border border-line2 bg-rail px-2 py-1 text-[11px] text-ink">
      {money(payload[0].value)}
    </div>
  );
}

/** Snapshots arrive newest first. They are reversed to chronological order and
    capped with the live total, so the right edge of the line tracks the stream. */
export function PnlChart({
  snapshots,
  liveValue,
}: {
  snapshots: Snapshot[];
  liveValue: number;
}) {
  const historic = [...snapshots]
    .reverse()
    .map((snapshot, index) => ({ index, value: snapshot.total_value }));
  const data =
    liveValue > 0
      ? [...historic, { index: historic.length, value: liveValue }]
      : historic;

  const first = data[0]?.value ?? 0;
  const last = data[data.length - 1]?.value ?? 0;
  const changePercent = first === 0 ? 0 : ((last - first) / first) * 100;
  const positive = last >= first;

  return (
    <Panel
      label="portfolio value"
      accent="gold"
      meta={
        data.length ? (
          <span className={positive ? "text-up" : "text-down"}>
            {percent(changePercent)}
          </span>
        ) : null
      }
      className="min-w-0 flex-1 border-l border-line"
      bodyClassName="p-2"
    >
      <div data-testid="pnl-chart" className="h-full w-full">
        {data.length < 2 ? (
          <div className="flex h-full items-center justify-center text-[11px] tracking-[0.16em] text-dim">
            AWAITING SNAPSHOTS
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={data}
              margin={{ top: 6, right: 8, bottom: 4, left: 0 }}
            >
              <CartesianGrid stroke="#1c2634" strokeDasharray="2 4" />
              <YAxis
                domain={["dataMin", "dataMax"]}
                width={62}
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#7f8b9e", fontSize: 10 }}
                tickFormatter={(value: number) => value.toFixed(0)}
              />
              <Tooltip content={<PnlTooltip />} cursor={{ stroke: "#33415a" }} />
              <Line
                type="monotone"
                dataKey="value"
                stroke="#ecad0a"
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </Panel>
  );
}
