/**
 * The map's filters. They live in the URL (shareable), go to the tile server as the same
 * query string, and to `/api/v1/properties` for the synced list. Defaults match the server:
 * market sales only, every year, any type, places known at least to their locality.
 */
export type SaleType = "any" | "new" | "second_hand";
export type MinConfidence = "exact" | "street" | "locality" | "routing_key" | "county";

export interface Filters {
  priceMin: number | null;
  priceMax: number | null;
  dateFrom: string | null;
  dateTo: string | null;
  type: SaleType;
  excludeNonMarket: boolean;
  excludeBulk: boolean;
  minConfidence: MinConfidence;
}

export const DEFAULT_FILTERS: Filters = {
  priceMin: null,
  priceMax: null,
  dateFrom: null,
  dateTo: null,
  type: "any",
  excludeNonMarket: true,
  excludeBulk: true,
  minConfidence: "locality",
};

const TYPES: SaleType[] = ["any", "new", "second_hand"];
const CONFIDENCES: MinConfidence[] = ["exact", "street", "locality", "routing_key", "county"];
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function num(v: string | null): number | null {
  if (v === null || v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

export function parseFilters(params: URLSearchParams): Filters {
  const type = params.get("type") as SaleType;
  const conf = params.get("minConfidence") as MinConfidence;
  const date = (k: string) => {
    const v = params.get(k);
    return v && ISO_DATE.test(v) ? v : null;
  };
  return {
    priceMin: num(params.get("priceMin")),
    priceMax: num(params.get("priceMax")),
    dateFrom: date("dateFrom"),
    dateTo: date("dateTo"),
    type: TYPES.includes(type) ? type : "any",
    excludeNonMarket: params.get("excludeNonMarket") !== "false",
    excludeBulk: params.get("excludeBulk") !== "false",
    minConfidence: CONFIDENCES.includes(conf) ? conf : "locality",
  };
}

/** Only what differs from the defaults, so default URLs (and cached tiles) stay short. */
export function filtersToParams(f: Filters): URLSearchParams {
  const p = new URLSearchParams();
  if (f.priceMin !== null) p.set("priceMin", String(f.priceMin));
  if (f.priceMax !== null) p.set("priceMax", String(f.priceMax));
  if (f.dateFrom) p.set("dateFrom", f.dateFrom);
  if (f.dateTo) p.set("dateTo", f.dateTo);
  if (f.type !== "any") p.set("type", f.type);
  if (!f.excludeNonMarket) p.set("excludeNonMarket", "false");
  if (!f.excludeBulk) p.set("excludeBulk", "false");
  if (f.minConfidence !== "locality") p.set("minConfidence", f.minConfidence);
  return p;
}
