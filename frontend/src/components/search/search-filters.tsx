"use client";

import { PriceInput } from "@/components/map/filter-panel";
import { type Filters, type MinConfidence, RADII, type SaleType, type Vat } from "@/lib/filters";
import { formatDistance } from "@/lib/format";

const input = "mt-0.5 w-full px-2.5 py-1.5";
const legend = "font-mono text-xs font-semibold uppercase tracking-[0.08em] text-muted";
const DISTANCES = [250, 500, 1000, 2000];

function DistanceSelect({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number | null;
  onChange: (v: number | null) => void;
}) {
  return (
    <label className="block">
      <span className="text-muted">{label}</span>
      <select
        className={input}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
      >
        <option value="">Any distance</option>
        {DISTANCES.map((d) => (
          <option key={d} value={d}>
            Within {formatDistance(d)}
          </option>
        ))}
      </select>
    </label>
  );
}

/** Every search filter the brief lists, except the places, which are chosen above. */
export function SearchFilters({
  filters,
  onChange,
}: {
  filters: Filters;
  onChange: (f: Filters) => void;
}) {
  const set = <K extends keyof Filters>(key: K, value: Filters[K]) =>
    onChange({ ...filters, [key]: value });
  return (
    <form
      aria-label="Filter sales"
      className="space-y-5 text-sm"
      onSubmit={(e) => e.preventDefault()}
    >
      {filters.near ? (
        <fieldset className="space-y-2">
          <legend className={legend}>Distance</legend>
          <label className="block">
            <span className="text-muted">Within</span>
            <select
              className={input}
              value={filters.radiusM ?? 1000}
              onChange={(e) => set("radiusM", Number(e.target.value))}
            >
              {RADII.map((r) => (
                <option key={r} value={r}>
                  {formatDistance(r)}
                </option>
              ))}
            </select>
          </label>
        </fieldset>
      ) : null}
      <fieldset className="space-y-2">
        <legend className={legend}>Price and date</legend>
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
      </fieldset>
      <fieldset className="space-y-2">
        <legend className={legend}>Property</legend>
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
      </fieldset>
      <fieldset className="space-y-2">
        <legend className={legend}>Nearby</legend>
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
      </fieldset>
      <fieldset className="space-y-2">
        <legend className={legend}>Which sales</legend>
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
