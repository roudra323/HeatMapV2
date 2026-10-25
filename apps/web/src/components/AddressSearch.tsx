"use client";

import { useRouter } from "next/navigation";
import { useId, useState, type FormEvent } from "react";

import { SearchIcon } from "./icons";

const ADDRESS = /^0x[0-9a-fA-F]{40}$/;

/** Jump straight to a wallet page by address. */
export function AddressSearch({ compact = false }: { compact?: boolean }) {
  const router = useRouter();
  const id = useId();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string>();

  function submit(e: FormEvent) {
    e.preventDefault();
    const address = value.trim();
    if (!ADDRESS.test(address)) {
      setError("Enter a full address: 0x followed by 40 hex characters.");
      return;
    }
    setError(undefined);
    setValue("");
    router.push(`/wallets/${address.toLowerCase()}`);
  }

  return (
    <form onSubmit={submit} role="search" className="relative w-full">
      <label htmlFor={id} className={compact ? "sr-only" : "mb-1 block text-xs font-medium text-muted"}>
        Open a wallet
      </label>
      <div className="relative">
        <SearchIcon className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted" />
        <input
          id={id}
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            if (error) setError(undefined);
          }}
          placeholder={compact ? "Open a wallet by address" : "0x…"}
          spellCheck={false}
          autoComplete="off"
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-err` : undefined}
          className={`mono w-full rounded-md border bg-surface-2 py-2 pr-3 pl-9 text-sm placeholder:font-sans placeholder:text-muted ${
            error ? "border-danger" : "border-line-strong"
          } ${compact ? "min-h-9" : "min-h-10"}`}
        />
      </div>
      {error && (
        <p id={`${id}-err`} role="alert" className={`mt-1 text-xs text-danger ${compact ? "absolute top-full rounded bg-surface px-1 shadow" : ""}`}>
          {error}
        </p>
      )}
    </form>
  );
}
