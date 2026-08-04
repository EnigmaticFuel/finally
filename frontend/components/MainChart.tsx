"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  YAxis,
} from "recharts";
import { Panel } from "./Panel";
import { percent, price } from "@/lib/format";
import type { PriceUpdate } from "@/lib/types";

function ChartTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { value: number }[];
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="border border-line2 bg-rail px-2 py-1 text-[11px] text-ink">
      {price(payload[0].value)}
    </div>
  );
}

export function MainChart({
  ticker,
  points,
  quote,
}: {
  ticker: string | null;
  points: number[];
  quote?: PriceUpdate;
}) {
  const data = points.map((value, index) => ({ index, value }));
  const change = quote?.change_from_open_percent ?? 0;
  const positive = change >= 0;
  const stroke = positive ? "#26c281" : "#f0454b";

  return (
    <Panel
      label={ticker ? `${ticker} · session` : "market"}
      accent="azure"
      meta={
        quote ? (
          <span className={positive ? "text-up" : "text-down"}>
            {price(quote.price)} {percent(change)}
          </span>
        ) : null
      }
      className="min-h-0 flex-1"
      bodyClassName="p-2"
    >
      <div data-testid="main-chart" className="h-full w-full">
        {data.length < 2 ? (
          <div className="flex h-full items-center justify-center text-[11px] tracking-[0.16em] text-dim">
            SELECT A TICKER
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={data}
              margin={{ top: 6, right: 8, bottom: 4, left: 0 }}
            >
              <defs>
                <linearGradient id="mainFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={stroke} stopOpacity={0.28} />
                  <stop offset="100%" stopColor={stroke} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#1c2634" strokeDasharray="2 4" />
              <YAxis
                domain={["dataMin", "dataMax"]}
                width={54}
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#7f8b9e", fontSize: 10 }}
                tickFormatter={price}
              />
              {quote ? (
                <ReferenceLine
                  y={quote.open_price}
                  stroke="#4f5a6b"
                  strokeDasharray="3 3"
                />
              ) : null}
              <Tooltip content={<ChartTooltip />} cursor={{ stroke: "#33415a" }} />
              <Area
                type="monotone"
                dataKey="value"
                stroke={stroke}
                strokeWidth={1.5}
                fill="url(#mainFill)"
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </Panel>
  );
}
