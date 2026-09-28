"use client";

import { useEffect, useState } from "react";

import type { Filters, MinConfidence, SaleType } from "@/lib/filters";

// Borders, radius and colours come from the base form styles (globals.css).
const input = "mt-0.5 w-full px-2.5 py-1.5";

/** Number fields apply after a short pause so every keystroke is not a new set of tiles. */
function PriceInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number | null;
  onChange: (v: number | null) => void;
}) {
  const [text, setText] = useState(value === null ? "" : String(value));
  // A new value from outside (the URL, a reset) replaces what is typed.
  const [shown, setShown] = useState(value);
  if (value !== shown) {
    setShown(value);
    setText(value === null ? "" : String(value));
  }
  useEffect(() => {
    const t = setTimeout(() => {
      const n = text.trim() === "" ? null : Number(text);
      if (n === null || (Number.isFinite(n) && n >= 0)) {
        if (n !== value) onChange(n);
      }
    }, 500);
    return () => clearTimeout(t);
  }, [text, value, onChange]);
  return (
    <label className="block">
      <span className="text-muted">{label}</span>
      <input
        className={input}
        inputMode="numeric"
        type="number"
        min={0}
        step={10000}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
    </label>
  );
}

export function FilterPanel({
  filters,
  onChange,
  showHexes,
  onShowHexes,
}: {
  filters: Filters;
  onChange: (f: Filters) => void;
  showHexes: boolean;
  onShowHexes: (v: boolean) => void;
}) {
  const set = <K extends keyof Filters>(key: K, value: Filters[K]) =>
    onChange({ ...filters, [key]: value });
  return (
    <form
      aria-label="Filter sales"
      className="space-y-3 text-sm"
      onSubmit={(e) => e.preventDefault()}
    >
      <fieldset className="space-y-1">
        <legend className="font-mono text-xs font-semibold uppercase tracking-[0.08em] text-muted">
          Layer
        </legend>
        <label className="flex items-center gap-2">
          <input
            type="radio"
            name="layer"
            checked={!showHexes}
            onChange={() => onShowHexes(false)}
          />
          Individual sales
        </label>
        <label className="flex items-center gap-2">
          <input type="radio" name="layer" checked={showHexes} onChange={() => onShowHexes(true)} />
          Median price by area (last 12 months)
        </label>
      </fieldset>
      <fieldset className="space-y-2" disabled={showHexes}>
        <legend className="font-mono text-xs font-semibold uppercase tracking-[0.08em] text-muted">
          Sales
        </legend>
        <div className="grid grid-cols-2 gap-2">
          <PriceInput
            label="Price from (€)"
            value={filters.priceMin}
            onChange={(v) => set("priceMin", v)}
          />
          <PriceInput
            label="Price to (€)"
            value={filters.priceMax}
            onChange={(v) => set("priceMax", v)}
          />
          <label className="block">
            <span className="text-muted">Sold from</span>
            <input
              className={input}
              type="date"
              min="2010-01-01"
              value={filters.dateFrom ?? ""}
              onChange={(e) => set("dateFrom", e.target.value || null)}
            />
          </label>
          <label className="block">
            <span className="text-muted">Sold to</span>
            <input
              className={input}
              type="date"
              min="2010-01-01"
              value={filters.dateTo ?? ""}
              onChange={(e) => set("dateTo", e.target.value || null)}
            />
          </label>
        </div>
        <label className="block">
          <span className="text-muted">Type</span>
          <select
            className={input}
            value={filters.type}
            onChange={(e) => set("type", e.target.value as SaleType)}
          >
            <option value="any">New and second-hand</option>
            <option value="new">New builds only</option>
            <option value="second_hand">Second-hand only</option>
          </select>
        </label>
        <label className="block">
          <span className="text-muted">Location precision</span>
          <select
            className={input}
            value={filters.minConfidence}
            onChange={(e) => set("minConfidence", e.target.value as MinConfidence)}
          >
            <option value="exact">Exact address only</option>
            <option value="street">Street or better</option>
            <option value="locality">Town, village or townland or better</option>
            <option value="county">Everything, including county only</option>
          </select>
        </label>
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            checked={!filters.excludeNonMarket}
            onChange={(e) => set("excludeNonMarket", !e.target.checked)}
          />
          Include sales not at full market price
        </label>
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            checked={!filters.excludeBulk}
            onChange={(e) => set("excludeBulk", !e.target.checked)}
          />
          Include bulk and portfolio sales
        </label>
      </fieldset>
    </form>
  );
}
