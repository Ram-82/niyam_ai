import "./globals.css";
import type { Metadata } from "next";
import { Archivo, IBM_Plex_Mono, Zilla_Slab } from "next/font/google";


// Three roles, three families (per Claude Design bundler spec).
//   sans  — Archivo    (body, labels, controls, wordmark)
//   serif — Zilla Slab (page titles, hero labels)
//   mono  — IBM Plex Mono (money, scores, GSTINs, invoice numbers, periods, dates)
//
// Weight 400 + 600 only — anything else is a token violation.
const archivo = Archivo({
  subsets: ["latin"],
  weight: ["400", "600"],
  display: "swap",
  variable: "--font-sans",
});

const zillaSlab = Zilla_Slab({
  subsets: ["latin"],
  weight: ["400", "600"],
  display: "swap",
  variable: "--font-serif",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "600"],
  display: "swap",
  variable: "--font-mono",
});


export const metadata: Metadata = {
  title: "Niyam AI",
  description: "GST pre-filing intelligence for CA firms",
};


export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${archivo.variable} ${zillaSlab.variable} ${plexMono.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
