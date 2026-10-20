"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "./api";

type Query = Record<string, string | number | boolean | undefined>;

export interface ApiState<T> {
  data: T | undefined;
  error: string | undefined;
  loading: boolean;
  reload: () => void;
}

interface Resolved<T> {
  key: string | null;
  data?: T;
  error?: string;
}

/** Fetch ``path`` whenever it or ``query`` changes; previous data stays visible while reloading. */
export function useApi<T>(path: string | null, query?: Query): ApiState<T> {
  const [tick, setTick] = useState(0);
  const queryKey = JSON.stringify(query ?? {});
  const requestKey = path === null ? null : `${path}?${queryKey}#${tick}`;
  const [resolved, setResolved] = useState<Resolved<T>>({ key: null });

  useEffect(() => {
    if (path === null || requestKey === null) return;
    let cancelled = false;
    api
      .get<T>(path, JSON.parse(queryKey) as Query)
      .then((data) => {
        if (!cancelled) setResolved({ key: requestKey, data });
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setResolved({ key: requestKey, error: e instanceof Error ? e.message : String(e) });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [path, queryKey, requestKey]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return {
    data: resolved.data,
    error: resolved.key === requestKey ? resolved.error : undefined,
    loading: requestKey !== null && resolved.key !== requestKey,
    reload,
  };
}
