"use client";

import { useEffect, useRef, useState } from "react";
import { price } from "@/lib/format";

/** Flashes green or red for ~500ms whenever the value changes. The sequence
    number remounts the span so a run of upticks re-triggers the animation. */
export function PriceCell({
  value,
  testId,
  className = "",
}: {
  value: number;
  testId?: string;
  className?: string;
}) {
  const previous = useRef(value);
  const [flash, setFlash] = useState({ cls: "", seq: 0 });

  useEffect(() => {
    if (value === previous.current) return;
    const cls = value > previous.current ? "flash-up" : "flash-down";
    previous.current = value;
    setFlash((current) => ({ cls, seq: current.seq + 1 }));
    const timer = setTimeout(
      () => setFlash((current) => ({ ...current, cls: "" })),
      500,
    );
    return () => clearTimeout(timer);
  }, [value]);

  return (
    <span
      key={flash.seq}
      data-testid={testId}
      className={`inline-block rounded-xs px-1 ${flash.cls} ${className}`}
    >
      {price(value)}
    </span>
  );
}
