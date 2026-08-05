/**
 * Canonical empty state. No screen ships without one.
 *
 * Contract: title + one sentence explaining what will show up here +
 * (optionally) the next-action affordance the user can take right now.
 * No blank cards. No "no data" alone.
 */
import Link from "next/link";


export function EmptyState({
  title,
  body,
  action,
  testId,
}: {
  title: string;
  body: string;
  action?: { label: string; href?: string; onClick?: () => void };
  testId?: string;
}) {
  const btnCls =
    "inline-flex items-center gap-1 mt-4 px-3 py-1.5 rounded-md " +
    "bg-accent text-paper-raised text-sm font-semibold " +
    "hover:bg-accent-hover transition-colors duration-fast";
  return (
    <div
      className="text-center px-6 py-10 text-ink-muted"
      data-testid={testId ?? "empty-state"}
    >
      <div className="text-ink font-semibold text-lg">{title}</div>
      <p className="mt-1 text-sm max-w-md mx-auto">{body}</p>
      {action?.href && (
        <Link href={action.href} className={btnCls}>
          {action.label} →
        </Link>
      )}
      {action?.onClick && !action.href && (
        <button type="button" onClick={action.onClick} className={btnCls}>
          {action.label}
        </button>
      )}
    </div>
  );
}
