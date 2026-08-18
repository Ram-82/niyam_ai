/* Shared empty-state renderer. Two variants:
 *   - "block" (default): 48px vertical padding, centered — for tables and
 *     full card content areas.
 *   - "inline": compact — for sub-rails, tab panels, side lists. */

type Props = {
  /** Primary message. Should end with a period. */
  message: string;
  /** Optional second line — hint or CTA copy. */
  hint?: string;
  /** Rendering density. Defaults to "block". */
  variant?: "block" | "inline";
};

export function EmptyState({ message, hint, variant = "block" }: Props) {
  const isBlock = variant === "block";
  return (
    <div
      style={{
        padding: isBlock ? "48px 16px" : "16px 12px",
        textAlign: isBlock ? "center" : "left",
        color: "var(--text-muted)",
        fontSize: 13,
        lineHeight: "18px",
      }}
    >
      <div>{message}</div>
      {hint && (
        <div style={{ marginTop: 4, fontSize: 12, color: "var(--text-muted)" }}>
          {hint}
        </div>
      )}
    </div>
  );
}
