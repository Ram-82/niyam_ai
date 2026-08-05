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
  return (
    <div className="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h1 className="font-serif text-display text-ink leading-tight">
          {title}
        </h1>
        {context && (
          <div className="text-base text-ink-muted mt-2">{context}</div>
        )}
      </div>
      {actions && <div className="flex items-center gap-3 mt-2">{actions}</div>}
    </div>
  );
}
