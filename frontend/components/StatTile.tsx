/**
 * Command-center summary tile — quiet by design.
 * <StatTile label="Returns this period" value="12" />
 *
 * Value can be arbitrary React (a mini ScoreBadge, an ITCCell, a
 * plain number) so tone comes from the value component, not the
 * tile itself.
 */
import type { ReactNode } from "react";


export function StatTile({
  label,
  value,
  emphasize,
  testId,
}: {
  label: string;
  value: ReactNode;
  /** Optional emphasis when the number is materially bad (e.g. overdue > 0). */
  emphasize?: "red" | "amber" | null;
  testId?: string;
}) {
  const emphasisCls =
    emphasize === "red"
      ? "border-red-fg/40"
      : emphasize === "amber"
      ? "border-amber-fg/40"
      : "border-rule";
  return (
    <div
      className={
        "bg-paper-raised border rounded-md px-4 py-3 flex flex-col justify-between min-h-[76px] " +
        emphasisCls
      }
      data-testid={testId}
    >
      <div className="text-xs uppercase tracking-wide text-ink-muted font-semibold">
        {label}
      </div>
      <div className="text-xl font-mono font-semibold text-ink mt-2">{value}</div>
    </div>
  );
}
