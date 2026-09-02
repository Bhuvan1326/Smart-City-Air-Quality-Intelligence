import "./globals.css";

import type { Metadata, Viewport } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";

import { Providers } from "@/components/providers";

/*
 * Geist for prose and UI, Geist Mono for every figure. Metric values render in
 * mono with tabular numerals (see globals.css) so animated counters and
 * refetched readings never shift the layout of their neighbours.
 *
 * Sourced from the `geist` package rather than next/font/google: it ships the
 * woff2 files locally, so the production build does not need to reach
 * fonts.gstatic.com and cannot fail on a network hiccup. Both exports declare
 * the same --font-geist-sans / --font-geist-mono variables globals.css expects.
 */

export const metadata: Metadata = {
  title: "Urban Air Quality Intelligence",
  description: "Smart City Air Quality Intelligence Platform",
  // public/manifest.json already existed but was never linked, so the PWA
  // install prompt and shortcuts could not be discovered.
  manifest: "/manifest.json",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f8fafc" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0f1a" },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // suppressHydrationWarning: next-themes writes the theme class onto <html>
    // before React hydrates, which is an intentional server/client mismatch.
    <html
      lang="en"
      suppressHydrationWarning
      className={`${GeistSans.variable} ${GeistMono.variable}`}
    >
      <body className="font-sans antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
