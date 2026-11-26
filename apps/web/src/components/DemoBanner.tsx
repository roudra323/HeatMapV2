"use client";

import { useEffect, useState } from "react";

import { DEMO, demoMeta } from "@/lib/demo";
import { date } from "@/lib/format";

const REPO = "https://github.com/roudra323/HeatMapV2";

/** A strip above the header saying the data is a synthetic, read-only snapshot. Demo mode only. */
export function DemoBanner() {
  const [taken, setTaken] = useState<string | null>(null);
  useEffect(() => {
    if (!DEMO) return;
    demoMeta()
      .then((m) => setTaken(m.generated_at))
      .catch(() => setTaken(null));
  }, []);
  if (!DEMO) return null;
  return (
    <div className="border-b border-line bg-primary-soft text-ink">
      <p className="mx-auto max-w-7xl px-4 py-2 text-[0.8125rem] leading-snug sm:px-6 lg:px-8">
        <span className="mr-2 inline-flex rounded-full bg-primary px-2 py-px text-[0.6875rem] font-semibold tracking-wide text-primary-ink uppercase">
          Demo
        </span>
        Synthetic wallets and swaps, read-only{taken ? `, snapshot taken ${date(taken)}` : ""}. The live version runs
        against Ethereum mainnet.{" "}
        <a href={REPO} className="font-medium text-primary underline underline-offset-2 hover:no-underline">
          Source on GitHub
        </a>
      </p>
    </div>
  );
}
