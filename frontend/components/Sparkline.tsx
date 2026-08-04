"use client";

import { Line, LineChart, YAxis } from "recharts";

const UP = "#26c281";
const DOWN = "#f0454b";

/** Fixed size rather than responsive: ten of these live in the watchlist and
    each one is a known 76x22 slot. */
export function Sparkline({
  points,
  positive,
  testId,
}: {
  points: number[];
  positive: boolean;
  testId?: string;
}) {
  if (points.length < 2) {
    return (
      <div
        data-testid={testId}
        className="flex h-[22px] w-[76px] items-center"
        aria-hidden
      >
        <span className="h-px w-full bg-line" />
      </div>
    );
  }

  const data = points.map((value, index) => ({ index, value }));

  return (
    <div data-testid={testId} className="h-[22px] w-[76px]" aria-hidden>
      <LineChart
        width={76}
        height={22}
        data={data}
        margin={{ top: 3, right: 1, bottom: 3, left: 1 }}
      >
        <YAxis hide domain={["dataMin", "dataMax"]} />
        <Line
          type="monotone"
          dataKey="value"
          stroke={positive ? UP : DOWN}
          strokeWidth={1.25}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </div>
  );
}
