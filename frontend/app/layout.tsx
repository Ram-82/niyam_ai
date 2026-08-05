import "./globals.css";
import type { Metadata } from "next";
import { Inter, IBM_Plex_Mono, Source_Serif_4 } from "next/font/google";


// Three roles, three families.
//   sans  — Inter        (body, labels, controls, wordmark)
//   serif — Source Serif 4 (page titles, hero labels — Claude-esque)
//   mono  — IBM Plex Mono (money, scores, GSTINs, invoice numbers, periods, dates)
//
// Weight 400 + 600 only — anything else is a token violation.
const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "600"],
  display: "swap",
  variable: "--font-sans",
});

const sourceSerif = Source_Serif_4({
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
      className={`${inter.variable} ${sourceSerif.variable} ${plexMono.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
