"use client";

import { useEffect, useState } from "react";

import { api, type Chain } from "./api";

const CHAIN = "ethereum";
let cached: Promise<string | null> | undefined;

function load(): Promise<string | null> {
  cached ??= api
    .get<Chain[]>("/v1/chains")
    .then((chains) => chains.find((c) => c.name === CHAIN)?.explorer_url ?? null)
    .catch(() => {
      cached = undefined;
      return null;
    });
  return cached;
}

/** Block explorer base URL for the active chain (e.g. https://etherscan.io), once loaded. */
export function useExplorer(): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    load().then((u) => {
      if (live) setUrl(u);
    });
    return () => {
      live = false;
    };
  }, []);
  return url;
}
