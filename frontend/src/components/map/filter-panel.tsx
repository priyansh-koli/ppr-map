"use client";

import { useEffect, useState } from "react";

import Link from "next/link";

import { slugLabel } from "@/lib/describe";
import {
  countyName,
  type Filters,
  filtersToParams,
  hasPlaceFilter,
  type MinConfidence,
  type SaleType,
  type Vat,
} from "@/lib/filters";
import { formatDistance } from "@/lib/format";
import { ROUTES } from "@/lib/routes";

// Borders, radius and colours come from the base form styles (globals.css).
const input = "mt-0.5 w-full px-2.5 py-1.5";

/** Number fields apply after a short pause so every keystroke is not a new set of tiles. */
export function PriceInput({
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

const DISTANCES = [250, 500, 1000, 2000];

/** A maximum distance; a value from the URL that is not in the list is offered as well. */
export function DistanceSelect({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number | null;
  onChange: (v: number | null) => void;
}) {
  const options = value === null || DISTANCES.includes(value) ? DISTANCES : [...DISTANCES, value];
  return (
    <label className="block">
      <span className="text-muted">{label}</span>
      <select
        className={input}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
      >
        <option value="">Any distance</option>
        {[...options]
          .sort((a, b) => a - b)
          .map((d) => (
            <option key={d} value={d}>
              Within {formatDistance(d)}
            </option>
          ))}
      </select>
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
  // Place filters come from a search (D-047); here they can only be removed.
  const places = [
    ...filters.county.map((c) => ({
      label: `Co. ${countyName(c)}`,
      drop: () =>
        set(
          "county",
          filters.county.filter((x) => x !== c),
        ),
    })),
    ...filters.area.map((a) => ({
      label: slugLabel(a),
      drop: () =>
        set(
          "area",
          filters.area.filter((x) => x !== a),
        ),
    })),
    ...filters.routingKey.map((k) => ({
      label: k,
      drop: () =>
        set(
          "routingKey",
          filters.routingKey.filter((x) => x !== k),
        ),
    })),
    ...(filters.near
      ? [
          {
            label: `Within ${formatDistance(filters.radiusM ?? 1000)} of a point`,
            drop: () => onChange({ ...filters, near: null, radiusM: null }),
          },
        ]
      : []),
  ];
  return (
    <form
      aria-label="Filter sales"
      className="space-y-3 text-sm"
      onSubmit={(e) => e.preventDefault()}
    >
      {hasPlaceFilter(filters) ? (
        <fieldset className="space-y-1">
          <legend className="font-mono text-xs font-semibold uppercase tracking-[0.08em] text-muted">
            Places
          </legend>
          <p className="text-muted">Only sales in:</p>
          <ul className="flex flex-wrap gap-1.5">
            {places.map((p) => (
              <li key={p.label} className="chip gap-1.5 pr-1">
                {p.label}
                <button
                  type="button"
                  onClick={p.drop}
                  aria-label={`Remove ${p.label}`}
                  className="grid h-5 w-5 place-items-center rounded-full hover:bg-fill"
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
          <Link
            className="text-accent underline"
            href={`${ROUTES.search.path}?${filtersToParams(filters).toString()}`}
          >
            Change in search
          </Link>
        </fieldset>
      ) : null}
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
          <span className="text-muted">VAT</span>
          <select
            className={input}
            value={filters.vat}
            onChange={(e) => set("vat", e.target.value as Vat)}
          >
            <option value="any">Any</option>
            <option value="exclusive">Filed without VAT (new builds)</option>
            <option value="inclusive">Filed with VAT or none due</option>
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
            <option value="routing_key">Eircode area or better</option>
            <option value="county">Everything, including county only</option>
          </select>
        </label>
        <DistanceSelect
          label="Nearest bus, Luas or rail stop"
          value={filters.maxStopM}
          onChange={(v) => set("maxStopM", v)}
        />
        <DistanceSelect
          label="Nearest school"
          value={filters.maxSchoolM}
          onChange={(v) => set("maxSchoolM", v)}
        />
        {filters.maxStopM !== null || filters.maxSchoolM !== null ? (
          <p className="text-xs text-muted">
            Straight-line distances, known only for sales placed at their house or street.
          </p>
        ) : null}
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
