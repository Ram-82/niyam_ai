/**
 * Consistent title block for every app page.
 * Left: title + one-line context. Right: page-level actions.
 */

export function PageHeader({
  title,
  context,
  actions,
}: {
  title: React.ReactNode;
  context?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  // Design spec: 30px serif (Zilla Slab) title with tight tracking
  // (-0.01em) and 1.1 line-height; 14px muted subtitle 5px below.
  return (
    <div className="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h1
          className="font-serif font-semibold text-ink"
          style={{ fontSize: "30px", lineHeight: 1.1, letterSpacing: "-0.01em" }}
        >
          {title}
        </h1>
        {context && (
          <div className="text-[14px] text-ink-muted mt-[5px]">{context}</div>
        )}
      </div>
      {actions && <div className="flex items-center gap-3 mt-2">{actions}</div>}
    </div>
  );
}
