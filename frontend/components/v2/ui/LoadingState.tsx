/* Shared loading placeholder — used when an entire content area is
 * pending. Matches EmptyState's shape so swapping between the two doesn't
 * cause layout shift.
 *
 * For short in-context swaps (e.g. `{loading ? "…" : count}` in a header)
 * keep the one-liner; this component is for standalone blocks. */

type Props = {
  /** Optional custom message. Defaults to "Loading…". */
  message?: string;
  /** Rendering density. Defaults to "block". */
  variant?: "block" | "inline";
};

export function LoadingState({ message = "Loading…", variant = "block" }: Props) {
  const isBlock = variant === "block";
  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        padding: isBlock ? "48px 16px" : "16px 12px",
        textAlign: isBlock ? "center" : "left",
        color: "var(--text-muted)",
        fontSize: 13,
        lineHeight: "18px",
      }}
    >
      {message}
    </div>
  );
}
