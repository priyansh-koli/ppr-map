/**
 * A search in words, for history, saved searches and alert emails' subjects:
 * "Cork, Kerry · €200k–€400k · new builds · sold 2024 on · newest first".
 */
import {
  countyName,
  DEFAULT_FILTERS,
  type Filters,
  parseFilters,
  parseSort,
  type Sort,
} from "./filters";
import { formatDate, formatDistance } from "./format";

const SORT_LABEL: Record<Sort, string> = {
  "-date": "newest first",
  date: "oldest first",
  "-price": "dearest first",
  price: "cheapest first",
  "-change": "biggest rise first",
  change: "biggest fall first",
};

/** "carlow-1f4955" → "Carlow", "ed-carlow-rural-a1b2c3" → "Carlow Rural", "sa-017010016" → "Small Area 017010016". */
export function slugLabel(slug: string): string {
  if (slug.startsWith("sa-")) return `Small Area ${slug.slice(3)}`;
  const words = slug
    .replace(/^(ed|townland)-/, "")
    .replace(/-[0-9a-f]{6}$/, "")
    .split("-")
    .filter(Boolean);
  return words.map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
}

/** €250k, €1.2m: short amounts for a one-line summary. */
export function shortEur(n: number): string {
  const trim = (v: number) => String(Math.round(v * 10) / 10);
  if (n >= 1_000_000) return `€${trim(n / 1_000_000)}m`;
  if (n >= 1000) return `€${trim(n / 1000)}k`;
  return `€${n}`;
}

function priceRange(f: Filters): string | null {
  if (f.priceMin !== null && f.priceMax !== null)
    return `${shortEur(f.priceMin)}–${shortEur(f.priceMax)}`;
  if (f.priceMin !== null) return `from ${shortEur(f.priceMin)}`;
  if (f.priceMax !== null) return `up to ${shortEur(f.priceMax)}`;
  return null;
}

function dates(f: Filters): string | null {
  if (f.dateFrom && f.dateTo) return `sold ${formatDate(f.dateFrom)} to ${formatDate(f.dateTo)}`;
  if (f.dateFrom) return `sold from ${formatDate(f.dateFrom)}`;
  if (f.dateTo) return `sold up to ${formatDate(f.dateTo)}`;
  return null;
}

export function describeSearch(
  query: Record<string, string>,
  names: Record<string, string> = {},
): string {
  const params = new URLSearchParams(query);
  // The user's own location is stored only as a marker (docs/permissions.md).
  const mine = params.get("near") === "my-location";
  if (mine) params.delete("near");
  const f = parseFilters(params);
  const sort = parseSort(params);
  const parts: (string | null)[] = [
    ...f.area.map((s) => names[s] ?? slugLabel(s)),
    f.county.length ? f.county.map(countyName).join(", ") : null,
    f.routingKey.length ? f.routingKey.join(", ") : null,
    mine || f.near
      ? `within ${formatDistance(Number(params.get("radiusM") ?? f.radiusM ?? 1000))} of ${
          mine ? "my location" : "a point"
        }`
      : null,
    priceRange(f),
    f.type === "new" ? "new builds" : f.type === "second_hand" ? "second-hand" : null,
    dates(f),
    f.vat === "exclusive" ? "VAT-exclusive prices" : null,
    f.vat === "inclusive" ? "prices with VAT" : null,
    f.maxStopM !== null ? `stop within ${formatDistance(f.maxStopM)}` : null,
    f.maxSchoolM !== null ? `school within ${formatDistance(f.maxSchoolM)}` : null,
    !f.excludeNonMarket ? "incl. non-market" : null,
    !f.excludeBulk ? "incl. bulk" : null,
    f.minConfidence !== DEFAULT_FILTERS.minConfidence
      ? `located to ${f.minConfidence.replace("_", " ")} or better`
      : null,
    sort !== "-date" ? SORT_LABEL[sort] : null,
  ];
  const text = parts.filter(Boolean).join(" · ");
  return text || "All sales in Ireland";
}
