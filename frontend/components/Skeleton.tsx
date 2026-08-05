/**
 * Loading placeholders. Two variants:
 *
 *   <SkeletonTable rows={5} cols={7} />       — for tables
 *   <SpinnerLabel label="Reconciling against GSTR-2B…" />  — engine triggers
 *
 * Respects prefers-reduced-motion (the pulse animation is disabled
 * via the CSS token file's media query).
 */

export function SkeletonTable({ rows = 5, cols = 6 }: { rows?: number; cols?: number }) {
  return (
    <div
      className="bg-paper-raised border border-rule rounded-md overflow-hidden"
      data-testid="skeleton-table"
      aria-busy="true"
      aria-live="polite"
    >
      <div className="border-b border-rule bg-paper h-8" />
      <div className="divide-y divide-rule">
        {Array.from({ length: rows }).map((_, r) => (
          <div key={r} className="flex px-3 py-2 gap-3">
            {Array.from({ length: cols }).map((__, c) => (
              <div
                key={c}
                className="h-3 bg-grey-bg rounded-sm animate-pulse flex-1"
                style={{ animationDuration: "1400ms" }}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}


export function SpinnerLabel({ label }: { label: string }) {
  return (
    <div
      className="inline-flex items-center gap-2 text-sm text-ink-muted"
      role="status"
      aria-live="polite"
    >
      <svg
        width="14" height="14" viewBox="0 0 24 24"
        className="animate-spin"
        style={{ animationDuration: "800ms" }}
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="10" stroke="var(--rule)" strokeWidth="3" fill="none" />
        <path
          d="M22 12 A10 10 0 0 0 12 2"
          stroke="var(--accent)" strokeWidth="3" fill="none" strokeLinecap="round"
        />
      </svg>
      <span>{label}</span>
    </div>
  );
}
