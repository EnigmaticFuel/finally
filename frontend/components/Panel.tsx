"use client";

import type { ReactNode } from "react";

type Accent = "azure" | "gold" | "plum";

const ACCENT_BG: Record<Accent, string> = {
  azure: "bg-azure",
  gold: "bg-gold",
  plum: "bg-plum",
};

/** Every panel wears the same rail: an accent tab naming its domain, a label,
    a hairline rule, and a right-aligned live datum. */
export function Panel({
  label,
  accent,
  meta,
  actions,
  children,
  className = "",
  bodyClassName = "",
}: {
  label: string;
  accent: Accent;
  meta?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={`flex min-h-0 min-w-0 flex-col bg-panel ${className}`}>
      <header className="flex h-7 shrink-0 items-center gap-2 border-b border-line bg-rail px-2">
        <span className={`h-3 w-[2px] shrink-0 ${ACCENT_BG[accent]}`} />
        <h2 className="text-[10px] font-medium tracking-[0.18em] text-muted uppercase">
          {label}
        </h2>
        <span className="h-px min-w-2 flex-1 bg-line" />
        {meta ? <span className="text-[10px] text-dim">{meta}</span> : null}
        {actions}
      </header>
      <div className={`min-h-0 flex-1 ${bodyClassName}`}>{children}</div>
    </section>
  );
}
