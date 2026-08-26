import type { CSSProperties } from "react";

export type HealthTone = "success" | "warning" | "danger";

export function toneForScore(score: number): HealthTone {
  if (score >= 80) return "success";
  if (score >= 60) return "warning";
  return "danger";
}

const toneColor: Record<HealthTone, string> = {
  success: "var(--success)",
  warning: "var(--warning)",
  danger: "var(--danger)",
};

export function HealthTrack({
  score,
  width = 64,
  height = 4,
}: {
  score: number;
  width?: number;
  height?: number;
}) {
  const tone = toneForScore(score);
  const style: CSSProperties = {
    display: "inline-block",
    width,
    height,
    borderRadius: "var(--radius-pill)",
    background: "var(--border)",
    overflow: "hidden",
    verticalAlign: "middle",
  };
  return (
    <span style={style}>
      <span
        style={{
          display: "block",
          width: `${Math.max(0, Math.min(100, score))}%`,
          height,
          background: toneColor[tone],
        }}
      />
    </span>
  );
}
