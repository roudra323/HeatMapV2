"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ComponentType, SVGProps } from "react";

import { AddressSearch } from "./AddressSearch";
import { ChevronRight, CompassIcon, DashboardIcon, EyeIcon, ScatterIcon } from "./icons";

type Item = {
  href: string;
  label: string;
  step?: number;
  icon: ComponentType<SVGProps<SVGSVGElement> & { size?: number }>;
  match: (path: string) => boolean;
};

/* Overview, then the three steps of the flow in order. */
const ITEMS: Item[] = [
  { href: "/", label: "Overview", icon: DashboardIcon, match: (p) => p === "/" },
  { href: "/discover", label: "Discover", step: 1, icon: CompassIcon, match: (p) => p.startsWith("/discover") },
  {
    href: "/watchlist",
    label: "Watchlist",
    step: 2,
    icon: EyeIcon,
    match: (p) => p.startsWith("/watchlist"),
  },
  { href: "/clusters", label: "Clusters", step: 3, icon: ScatterIcon, match: (p) => p.startsWith("/clusters") },
];

function Logo() {
  return (
    <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="var(--ink)" />
      <rect x="6" y="6" width="5.5" height="5.5" rx="1" fill="var(--heat-1)" />
      <rect x="13.25" y="6" width="5.5" height="5.5" rx="1" fill="var(--heat-2)" />
      <rect x="20.5" y="6" width="5.5" height="5.5" rx="1" fill="var(--heat-3)" />
      <rect x="6" y="13.25" width="5.5" height="5.5" rx="1" fill="var(--heat-2)" />
      <rect x="13.25" y="13.25" width="5.5" height="5.5" rx="1" fill="var(--heat-4)" />
      <rect x="20.5" y="13.25" width="5.5" height="5.5" rx="1" fill="var(--heat-2)" />
      <rect x="6" y="20.5" width="5.5" height="5.5" rx="1" fill="var(--heat-3)" />
      <rect x="13.25" y="20.5" width="5.5" height="5.5" rx="1" fill="var(--heat-1)" />
      <rect x="20.5" y="20.5" width="5.5" height="5.5" rx="1" fill="var(--heat-1)" />
    </svg>
  );
}

export function SiteHeader() {
  const path = usePathname() ?? "/";
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface/95 backdrop-blur supports-[backdrop-filter]:bg-surface/85">
      <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 sm:px-6 lg:px-8">
        <Link href="/" className="flex min-h-14 shrink-0 items-center gap-2 rounded-md font-semibold tracking-[-0.01em]">
          <Logo />
          HeatMap
        </Link>
        <nav aria-label="Main" className="hidden flex-1 md:block">
          <ol className="flex items-center gap-1">
            {ITEMS.map((item, i) => {
              const active = item.match(path);
              return (
                <li key={item.href} className="flex items-center gap-1">
                  {item.step && item.step > 1 && <ChevronRight size={14} className="text-line-strong" />}
                  {i === 1 && <span aria-hidden="true" className="mx-2 h-5 w-px bg-line" />}
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={`relative inline-flex min-h-14 items-center gap-2 px-2.5 text-sm transition-colors duration-150 ${
                      active
                        ? "font-medium text-ink after:absolute after:inset-x-2 after:bottom-0 after:h-0.5 after:rounded-full after:bg-primary"
                        : "text-muted hover:text-ink"
                    }`}
                  >
                    {item.step ? (
                      <>
                        <span className="sr-only">Step {item.step}: </span>
                        <span
                          aria-hidden="true"
                          className={`num inline-flex h-5 w-5 items-center justify-center rounded-full text-[0.6875rem] font-semibold ${
                            active ? "bg-primary text-primary-ink" : "bg-surface-2 text-muted ring-1 ring-line-strong"
                          }`}
                        >
                          {item.step}
                        </span>
                      </>
                    ) : (
                      <item.icon />
                    )}
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ol>
        </nav>
        <div className="ml-auto hidden w-72 lg:block">
          <AddressSearch compact />
        </div>
      </div>
      {/* Phones and small tablets: a tab bar under the brand row. */}
      <nav aria-label="Main" className="border-t border-line md:hidden">
        <ul className="grid grid-cols-4">
          {ITEMS.map((item) => {
            const active = item.match(path);
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={`flex min-h-12 flex-col items-center justify-center gap-0.5 text-xs ${
                    active ? "font-medium text-primary" : "text-muted"
                  }`}
                >
                  <item.icon size={18} />
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </header>
  );
}
