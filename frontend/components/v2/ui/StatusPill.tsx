import type { CSSProperties } from "react";

export type StatusTone = "success" | "warning" | "danger" | "accent" | "neutral" | "blocker";

const toneStyle: Record<StatusTone, CSSProperties> = {
  success: { background: "var(--success-soft)", color: "var(--success)" },
  warning: { background: "var(--warning-soft)", color: "var(--warning)" },
  danger: { background: "var(--danger-soft)", color: "var(--danger)" },
  accent: { background: "var(--accent-soft)", color: "var(--accent)" },
  neutral: { background: "var(--surface)", color: "var(--text-secondary)", border: "1px solid var(--border)" },
  blocker: { background: "transparent", color: "var(--danger)", border: "1px solid var(--danger)" },
};

export function StatusPill({
  tone,
  children,
  style,
}: {
  tone: StatusTone;
  children: React.ReactNode;
  style?: CSSProperties;
}) {
  return (
    <span
      style={{
        display: "inline-block",
        padding: "3px 8px",
        borderRadius: "var(--radius-chip)",
        fontSize: "var(--fs-label)",
        lineHeight: "var(--lh-label)",
        fontWeight: "var(--fw-medium)",
        ...toneStyle[tone],
        ...style,
      }}
    >
      {children}
    </span>
  );
}
