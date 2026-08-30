import "./globals.css";

import type { Metadata } from "next";

import { Providers } from "@/components/providers";

export const metadata: Metadata = {
  title: "Urban Air Quality Intelligence",
  description: "Smart City Air Quality Intelligence Platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
      <html lang="en" suppressHydrationWarning> 
        <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}