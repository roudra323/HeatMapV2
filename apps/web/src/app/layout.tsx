import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import type { ReactNode } from "react";

import { SiteHeader } from "@/components/Nav";

import "./globals.css";

const sans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-sans",
  display: "swap",
});

const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "HeatMap", template: "%s | HeatMap" },
  description: "Find the people behind DEX trades, follow their wallets and group them by behaviour.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#151e2c" },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body className="min-h-dvh font-sans text-[0.9375rem] antialiased">
        <a
          href="#main"
          className="sr-only z-50 rounded-md bg-primary px-3 py-2 text-primary-ink focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
        >
          Skip to content
        </a>
        <SiteHeader />
        <main id="main" tabIndex={-1} className="mx-auto max-w-7xl px-4 pt-6 pb-16 outline-none sm:px-6 sm:pt-8 lg:px-8">
          {children}
        </main>
      </body>
    </html>
  );
}
