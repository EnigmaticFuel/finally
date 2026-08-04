"use client";

import { money, percent, signedMoney, toneClass } from "@/lib/format";
import type { ConnectionStatus } from "@/lib/types";

const DOT: Record<ConnectionStatus, { color: string; label: string }> = {
  live: { color: "bg-up", label: "LIVE" },
  degraded: { color: "bg-gold", label: "DEGRADED" },
  down: { color: "bg-down", label: "OFFLINE" },
};

function Stat({
  label,
  value,
  testId,
  className = "text-ink",
}: {
  label: string;
  value: string;
  testId?: string;
  className?: string;
}) {
  return (
    <div className="flex flex-col items-end leading-none">
      <span className="text-[9px] tracking-[0.18em] text-dim uppercase">
        {label}
      </span>
      <span data-testid={testId} className={`mt-1 text-[13px] ${className}`}>
        {value}
      </span>
    </div>
  );
}

export function Header({
  cash,
  totalValue,
  unrealizedPnl,
  status,
}: {
  cash: number;
  totalValue: number;
  unrealizedPnl: number;
  status: ConnectionStatus;
}) {
  const dot = DOT[status];
  const invested = totalValue - cash;
  const pnlPercent =
    invested - unrealizedPnl === 0
      ? 0
      : (unrealizedPnl / (invested - unrealizedPnl)) * 100;

  return (
    <header className="flex h-14 shrink-0 items-center gap-5 border-b border-line bg-panel px-4">
      <div className="flex items-center gap-2.5">
        <span className="h-4 w-4 bg-gold" />
        <span className="text-[15px] tracking-[0.32em] text-ink">FINALLY</span>
      </div>

      <div className="flex items-center gap-2">
        <span
          data-testid="connection-dot"
          data-status={status}
          title={`Price stream ${dot.label.toLowerCase()}`}
          className={`h-2 w-2 rounded-full ${dot.color}`}
        />
        <span className="text-[10px] tracking-[0.16em] text-muted">
          {dot.label}
        </span>
      </div>

      <span className="text-[10px] tracking-[0.16em] text-dim">
        SIMULATED SESSION
      </span>

      <div className="ml-auto flex items-center gap-7">
        <Stat
          label="Cash"
          value={money(cash)}
          testId="header-cash"
          className="text-[13px] text-muted"
        />
        <Stat
          label="Unrealized"
          value={`${signedMoney(unrealizedPnl)} ${percent(pnlPercent)}`}
          testId="header-unrealized"
          className={`text-[13px] ${toneClass(unrealizedPnl)}`}
        />
        <div className="flex flex-col items-end leading-none">
          <span className="text-[9px] tracking-[0.18em] text-dim uppercase">
            Total Value
          </span>
          <span
            data-testid="header-total"
            className="mt-1 text-[24px] tracking-tight text-ink"
          >
            {money(totalValue)}
          </span>
        </div>
      </div>
    </header>
  );
}
