export function Monogram({ initials, size = 32 }: { initials: string; size?: number }) {
  return (
    <span
      style={{
        width: size,
        height: size,
        flex: "none",
        borderRadius: "8px",
        background: "var(--accent-soft)",
        color: "var(--accent)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: "var(--fs-label)",
        fontWeight: "var(--fw-semi)",
      }}
    >
      {initials}
    </span>
  );
}

export function MiniAvatar({ initials, size = 24 }: { initials: string; size?: number }) {
  return (
    <span
      style={{
        width: size,
        height: size,
        flex: "none",
        borderRadius: "var(--radius-pill)",
        background: "var(--row-hover)",
        color: "var(--text-secondary)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: "10px",
        fontWeight: "var(--fw-semi)",
      }}
    >
      {initials}
    </span>
  );
}
