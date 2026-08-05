/**
 * Period navigator.
 *
 * Replaces the raw YYYYMM text input with a stepper + dropdown of the
 * last 12 months. Renders "Jun 2026" everywhere via ``formatPeriod``.
 * The wire format (YYYYMM) stays untouched — API calls still receive
 * ``202606``.
 *
 * Keyboard:
 *   ←     previous month
 *   →     next month
 *   Enter / Space on the label opens the dropdown
 *
 * The three interactive elements (prev button, label button, next
 * button) all take the standard focus ring from globals.css.
 */
"use client";
import { useEffect, useRef, useState } from "react";
import { formatPeriod } from "@/lib/format-date";


function shift(period: string, deltaMonths: number): string {
  if (!/^\d{6}$/.test(period)) return period;
  const y = parseInt(period.slice(0, 4), 10);
  const m = parseInt(period.slice(4, 6), 10);
  const total = y * 12 + (m - 1) + deltaMonths;
  const ny = Math.floor(total / 12);
  const nm = (total % 12) + 1;
  return `${String(ny).padStart(4, "0")}${String(nm).padStart(2, "0")}`;
}


function trailingPeriods(anchor: string, count: number): string[] {
  const out: string[] = [];
  for (let i = 0; i < count; i++) out.push(shift(anchor, -i));
  return out;
}


export function PeriodNav({
  value,
  onChange,
  testId = "period-nav",
}: {
  value: string;
  onChange: (period: string) => void;
  testId?: string;
}) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (!menuRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onEsc(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  function onKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowLeft") { e.preventDefault(); onChange(shift(value, -1)); }
    else if (e.key === "ArrowRight") { e.preventDefault(); onChange(shift(value, 1)); }
  }

  const periods = trailingPeriods(value, 12);

  return (
    <div
      className="relative inline-flex items-center border border-rule rounded-sm bg-paper-raised"
      onKeyDown={onKey}
      data-testid={testId}
    >
      <button
        type="button"
        aria-label="Previous month"
        onClick={() => onChange(shift(value, -1))}
        className="px-2 py-1 text-ink-muted hover:text-ink border-r border-rule"
      >
        ‹
      </button>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="px-3 py-1 text-sm font-semibold text-ink min-w-[8rem] text-center"
        data-testid="period-input"
      >
        {formatPeriod(value)}
      </button>
      <button
        type="button"
        aria-label="Next month"
        onClick={() => onChange(shift(value, 1))}
        className="px-2 py-1 text-ink-muted hover:text-ink border-l border-rule"
      >
        ›
      </button>

      {open && (
        <div
          ref={menuRef}
          role="listbox"
          className="absolute top-full right-0 mt-1 z-20 bg-paper-raised border border-rule rounded-sm shadow-md min-w-[10rem] py-1"
        >
          {periods.map((p) => (
            <button
              key={p}
              type="button"
              role="option"
              aria-selected={p === value}
              onClick={() => { onChange(p); setOpen(false); }}
              className={
                "w-full text-left px-3 py-1.5 text-sm hover:bg-accent-tint " +
                (p === value ? "text-accent font-semibold" : "text-ink")
              }
            >
              {formatPeriod(p)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
