import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Niyam AI",
  description: "GST pre-filing intelligence",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
