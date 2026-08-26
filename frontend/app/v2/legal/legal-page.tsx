"use client";

/*
 * Shared renderer for /v2/legal/{terms,dpa}.
 *
 * Fetches GET /legal/documents/{doc_type} and renders the exact bytes the
 * acceptance flow will hash. The version, content-hash, and effective-from
 * are surfaced verbatim in a header ribbon so the reader sees the same
 * receipt fields that a future acceptance record would carry — one
 * source of truth for the document text.
 *
 * Rendered as ``<pre>`` on purpose. No markdown-to-HTML pass: any parser
 * would strip whitespace or reflow text and the displayed bytes would
 * drift from the hashed bytes. If the placeholder .md's ``<!-- ... -->``
 * counsel-review preamble is present, the reader sees it — this is the
 * intended honest state until legal review lands.
 */

import { useEffect, useState } from "react";


const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";


type Doc = {
  doc_type: string;
  version: string;
  content_hash: string;
  effective_from: string;
  content: string;
};


export default function LegalPage({ docType, title }: { docType: "terms" | "dpa"; title: string }) {
  const [doc, setDoc] = useState<Doc | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/legal/documents/${docType}`, { cache: "no-store" })
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return (await r.json()) as Doc;
      })
      .then((d) => { if (!cancelled) setDoc(d); })
      .catch((e) => { if (!cancelled) setErr(String(e)); });
    return () => { cancelled = true; };
  }, [docType]);

  return (
    <div style={{ background: "var(--bg)", minHeight: "100vh", color: "var(--text-primary)" }}>
      <header style={{
        height: 64, borderBottom: "1px solid var(--border)",
        display: "flex", alignItems: "center", padding: "0 32px",
        background: "var(--surface)",
      }}>
        <a href="/v2/landing" style={{
          fontSize: 15, fontWeight: 600, textDecoration: "none",
          color: "var(--text-primary)",
        }}>Niyam AI</a>
      </header>

      <main style={{
        maxWidth: 800, margin: "0 auto", padding: "48px 32px 96px",
      }}>
        <h1 style={{ margin: 0, fontSize: 32, lineHeight: "40px", fontWeight: 600 }}>
          {title}
        </h1>

        {doc && (
          <div style={{
            marginTop: 16, marginBottom: 32,
            padding: "12px 16px",
            border: "1px solid var(--border)", borderRadius: 8,
            background: "var(--surface)",
            fontSize: 13, color: "var(--text-secondary)",
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          }}>
            <div>Version {doc.version} · effective {doc.effective_from}</div>
            <div style={{ marginTop: 4, wordBreak: "break-all" }}>
              content_hash: {doc.content_hash}
            </div>
          </div>
        )}

        {err && (
          <div style={{
            marginTop: 32, padding: 16, borderRadius: 8,
            background: "var(--surface)", border: "1px solid var(--border)",
            color: "var(--text-secondary)",
          }}>
            Document could not be loaded ({err}).
          </div>
        )}

        {doc && (
          <pre style={{
            marginTop: 24,
            padding: 24,
            border: "1px solid var(--border)", borderRadius: 8,
            background: "var(--surface)",
            fontSize: 14, lineHeight: "22px",
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
            whiteSpace: "pre-wrap", wordBreak: "break-word",
            color: "var(--text-primary)",
          }}>{doc.content}</pre>
        )}

        {!doc && !err && (
          <div style={{ marginTop: 32, color: "var(--text-muted)" }}>Loading…</div>
        )}
      </main>

      <footer style={{
        borderTop: "1px solid var(--border)",
        padding: "24px 32px",
        color: "var(--text-muted)",
        fontSize: 12,
      }}>
        <a href="/v2/legal/terms" style={{ color: "inherit", marginRight: 16, textDecoration: "none" }}>Terms</a>
        <a href="/v2/legal/dpa" style={{ color: "inherit", textDecoration: "none" }}>DPA</a>
      </footer>
    </div>
  );
}
