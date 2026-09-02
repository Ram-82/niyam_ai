/* Shared error banner. Adopted by every wired v2 screen so the shape and
 * Retry affordance stay identical whether the error came from a dashboard
 * fetch, a form submit, or a public health probe. */

type Props = {
  /** User-facing sentence. Do not include the word "Error:" — the banner colour + role="alert" convey severity. */
  message: string;
  /** If provided, renders a Retry button that calls this. */
  onRetry?: () => void;
  /** Optional label if a Retry synonym is needed (e.g. "Reload"). */
  retryLabel?: string;
};

export function ErrorBanner({ message, onRetry, retryLabel = "Retry" }: Props) {
  return (
    <div
      role="alert"
      style={{
        padding: "12px 16px",
        border: "1px solid var(--danger)",
        borderRadius: "var(--radius-input, 10px)",
        background: "var(--danger-soft)",
        color: "var(--danger)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 12,
        fontSize: 13,
        lineHeight: "18px",
      }}
    >
      <span style={{ flex: 1, minWidth: 0 }}>{message}</span>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="v2-focus"
          style={{
            flex: "none",
            border: "1px solid var(--danger)",
            background: "transparent",
            color: "var(--danger)",
            borderRadius: "var(--radius-chip, 6px)",
            padding: "4px 10px",
            fontSize: 12,
            fontWeight: 500,
            cursor: "pointer",
          }}
        >
          {retryLabel}
        </button>
      )}
    </div>
  );
}
