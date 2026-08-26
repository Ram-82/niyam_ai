/**
 * v2 foundation swatch page — proves tokens + fonts wired correctly
 * before we port any real screen. Delete this file (or route it as
 * /v2/tokens if useful) once the first real screen ships.
 */

const colorSwatches: { name: string; token: string; fg?: string }[] = [
  { name: "bg", token: "--bg" },
  { name: "surface", token: "--surface" },
  { name: "border", token: "--border" },
  { name: "border-strong", token: "--border-strong" },
  { name: "text-primary", token: "--text-primary", fg: "#fff" },
  { name: "text-secondary", token: "--text-secondary", fg: "#fff" },
  { name: "text-muted", token: "--text-muted" },
  { name: "accent", token: "--accent", fg: "#fff" },
  { name: "accent-soft", token: "--accent-soft" },
  { name: "success", token: "--success", fg: "#fff" },
  { name: "success-soft", token: "--success-soft" },
  { name: "warning", token: "--warning", fg: "#fff" },
  { name: "warning-soft", token: "--warning-soft" },
  { name: "danger", token: "--danger", fg: "#fff" },
  { name: "danger-soft", token: "--danger-soft" },
];

const typeScale: { name: string; sizeVar: string; lhVar: string; sample: string }[] = [
  { name: "hero (64/72)", sizeVar: "--fs-hero", lhVar: "--lh-hero", sample: "₹1,24,58,300" },
  { name: "display (32/40)", sizeVar: "--fs-display", lhVar: "--lh-display", sample: "Compliance health" },
  { name: "money-lg (28/36)", sizeVar: "--fs-money-lg", lhVar: "--lh-money-lg", sample: "₹43,00,000" },
  { name: "h1 (24/32)", sizeVar: "--fs-h1", lhVar: "--lh-h1", sample: "Dashboard" },
  { name: "h2 (18/28)", sizeVar: "--fs-h2", lhVar: "--lh-h2", sample: "Filings queue" },
  { name: "body-lg (17/28)", sizeVar: "--fs-body-lg", lhVar: "--lh-body-lg", sample: "Longer body copy for context" },
  { name: "body (14/20)", sizeVar: "--fs-body", lhVar: "--lh-body", sample: "Default app body text" },
  { name: "label (12/16)", sizeVar: "--fs-label", lhVar: "--lh-label", sample: "LABEL / CAPTION" },
  { name: "mono (13/20)", sizeVar: "--fs-mono", lhVar: "--lh-mono", sample: "27AAAPZ1234C1Z5" },
];

export default function V2FoundationPage() {
  return (
    <main
      style={{
        maxWidth: 1120,
        margin: "0 auto",
        padding: "var(--v2-space-7) var(--v2-space-5)",
        display: "grid",
        gap: "var(--v2-space-6)",
      }}
    >
      <header>
        <h1
          style={{
            fontSize: "var(--fs-display)",
            lineHeight: "var(--lh-display)",
            fontWeight: "var(--fw-semi)",
            letterSpacing: "var(--tr-display)",
            margin: 0,
          }}
        >
          Niyam AI — v2 foundation
        </h1>
        <p
          style={{
            color: "var(--text-secondary)",
            marginTop: "var(--v2-space-2)",
            fontSize: "var(--fs-body-lg)",
            lineHeight: "var(--lh-body-lg)",
          }}
        >
          Sanity check for the v2 token layer. Every swatch, type step, radius
          and shadow below reads from{" "}
          <code
            className="mono"
            style={{
              background: "var(--accent-soft)",
              padding: "2px 6px",
              borderRadius: "var(--radius-chip)",
            }}
          >
            lib/tokens-v2.css
          </code>
          . If any block looks wrong, the token is wrong — fix it there.
        </p>
      </header>

      {/* --- Color swatches ------------------------------------------------ */}
      <section>
        <h2 style={sectionTitleStyle}>Color</h2>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))",
            gap: "var(--v2-space-3)",
          }}
        >
          {colorSwatches.map((s) => (
            <div
              key={s.name}
              style={{
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-app-card)",
                overflow: "hidden",
                background: "var(--surface)",
                boxShadow: "var(--shadow-card)",
              }}
            >
              <div
                style={{
                  height: 72,
                  background: `var(${s.token})`,
                  color: s.fg ?? "var(--text-primary)",
                  display: "flex",
                  alignItems: "flex-end",
                  padding: "var(--v2-space-2) var(--v2-space-3)",
                  fontSize: "var(--fs-label)",
                }}
              >
                {s.name}
              </div>
              <div
                className="mono"
                style={{
                  padding: "var(--v2-space-2) var(--v2-space-3)",
                  color: "var(--text-muted)",
                  fontSize: "var(--fs-meta)",
                  borderTop: "1px solid var(--border)",
                }}
              >
                {s.token}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* --- Type scale ---------------------------------------------------- */}
      <section>
        <h2 style={sectionTitleStyle}>Type scale (Inter + JetBrains Mono)</h2>
        <div
          style={{
            display: "grid",
            gap: "var(--v2-space-3)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-app-card)",
            padding: "var(--v2-space-5)",
            background: "var(--surface)",
          }}
        >
          {typeScale.map((t) => (
            <div
              key={t.name}
              style={{
                display: "grid",
                gridTemplateColumns: "160px 1fr",
                alignItems: "baseline",
                gap: "var(--v2-space-4)",
              }}
            >
              <div
                style={{
                  color: "var(--text-muted)",
                  fontSize: "var(--fs-label)",
                }}
              >
                {t.name}
              </div>
              <div
                className={t.name.startsWith("mono") ? "mono" : undefined}
                style={{
                  fontSize: `var(${t.sizeVar})`,
                  lineHeight: `var(${t.lhVar})`,
                  fontWeight: "var(--fw-semi)",
                }}
              >
                {t.sample}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* --- Radius + shadow ---------------------------------------------- */}
      <section>
        <h2 style={sectionTitleStyle}>Radius + shadow</h2>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))",
            gap: "var(--v2-space-4)",
          }}
        >
          {[
            { name: "card / shadow-card", radius: "var(--radius-app-card)", shadow: "var(--shadow-card)" },
            { name: "input", radius: "var(--radius-input)", shadow: "none" },
            { name: "chip", radius: "var(--radius-chip)", shadow: "none" },
            { name: "modal", radius: "var(--radius-app-card)", shadow: "var(--shadow-modal)" },
            { name: "hero-preview", radius: "var(--radius-marketing-card)", shadow: "var(--shadow-hero-preview)" },
            { name: "auth-card", radius: "var(--radius-marketing-card)", shadow: "var(--shadow-auth-card)" },
          ].map((r) => (
            <div
              key={r.name}
              style={{
                background: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: r.radius,
                boxShadow: r.shadow,
                padding: "var(--v2-space-5)",
                textAlign: "center",
                fontSize: "var(--fs-label)",
                color: "var(--text-secondary)",
              }}
            >
              {r.name}
            </div>
          ))}
        </div>
      </section>

      <footer
        style={{
          color: "var(--text-muted)",
          fontSize: "var(--fs-meta)",
          borderTop: "1px solid var(--border)",
          paddingTop: "var(--v2-space-4)",
        }}
      >
        v1 tokens (paper / ink / amber) at /login. v2 tokens at /v2. They coexist.
      </footer>
    </main>
  );
}

const sectionTitleStyle: React.CSSProperties = {
  fontSize: "var(--fs-h1)",
  lineHeight: "var(--lh-h1)",
  fontWeight: "var(--fw-semi)",
  letterSpacing: "var(--tr-h1)",
  margin: "0 0 var(--v2-space-3) 0",
};
