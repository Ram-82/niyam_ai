import "./globals.css";
import "../lib/tokens-v2.css";
import type { Metadata } from "next";
import {
  Archivo,
  IBM_Plex_Mono,
  Inter,
  JetBrains_Mono,
  Zilla_Slab,
} from "next/font/google";


// v1 fonts (Archivo/ZillaSlab/PlexMono) power existing routes.
// v2 fonts (Inter/JetBrainsMono) power the new /v2 route group.
// Both sets ship on every page — declaring here lets next/font
// subset + preload once; usage costs come only from what's rendered.
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

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
  variable: "--font-v2-sans",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
  variable: "--font-v2-mono",
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
      className={`${archivo.variable} ${zillaSlab.variable} ${plexMono.variable} ${inter.variable} ${jetbrainsMono.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
