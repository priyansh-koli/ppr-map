/**
 * The search filters. They live in the URL (shareable), go to the tile server as the same
 * query string, and to `/api/v1/search` and `/api/v1/properties`, so the map, the synced list
 * and search results always agree (D-047). Defaults match the server: market sales only, every
 * year, any type, places known at least to their locality. Lists travel as one
 * comma-separated parameter (`county=cork,kerry`).
 */
export type SaleType = "any" | "new" | "second_hand";
export type MinConfidence = "exact" | "street" | "locality" | "routing_key" | "county";
export type Vat = "any" | "exclusive" | "inclusive";
export type Sort = "-date" | "date" | "-price" | "price" | "-change" | "change";

export interface Filters {
  priceMin: number | null;
  priceMax: number | null;
  dateFrom: string | null;
  dateTo: string | null;
  type: SaleType;
  excludeNonMarket: boolean;
  excludeBulk: boolean;
  minConfidence: MinConfidence;
  vat: Vat;
  county: string[];
  area: string[];
  routingKey: string[];
  /** "lat,lng" */
  near: string | null;
  radiusM: number | null;
  maxStopM: number | null;
  maxSchoolM: number | null;
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
  vat: "any",
  county: [],
  area: [],
  routingKey: [],
  near: null,
  radiusM: null,
  maxStopM: null,
  maxSchoolM: null,
};

export const COUNTIES = [
  "carlow",
  "cavan",
  "clare",
  "cork",
  "donegal",
  "dublin",
  "galway",
  "kerry",
  "kildare",
  "kilkenny",
  "laois",
  "leitrim",
  "limerick",
  "longford",
  "louth",
  "mayo",
  "meath",
  "monaghan",
  "offaly",
  "roscommon",
  "sligo",
  "tipperary",
  "waterford",
  "westmeath",
  "wexford",
  "wicklow",
] as const;

const SORTS: Sort[] = ["-date", "date", "-price", "price", "-change", "change"];
export const RADII = [250, 500, 1000, 2000, 5000, 10000, 20000];

const TYPES: SaleType[] = ["any", "new", "second_hand"];
const CONFIDENCES: MinConfidence[] = ["exact", "street", "locality", "routing_key", "county"];
const VATS: Vat[] = ["any", "exclusive", "inclusive"];
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const ROUTING_KEY = /^(?:[AC-FHKNPRTV-Y]\d{2}|D6W)$/;
const SLUG = /^[a-z0-9_-]{1,80}$/;
const NEAR = /^\d{2}(\.\d{1,7})?,-\d{1,2}(\.\d{1,7})?$/;

/** "2025-02-30" has the right shape but is not a day. */
function isCalendarDate(v: string): boolean {
  if (!ISO_DATE.test(v)) return false;
  const d = new Date(`${v}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === v;
}

function num(v: string | null, min = 0, max = Infinity): number | null {
  if (v === null || v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) && n >= min && n <= max ? n : null;
}

function list(v: string | null, keep: (item: string) => boolean): string[] {
  if (!v) return [];
  return [...new Set(v.split(",").map((s) => s.trim()))].filter((s) => s && keep(s));
}

function near(v: string | null): string | null {
  if (!v || !NEAR.test(v)) return null;
  const [lat = NaN, lng = NaN] = v.split(",").map(Number);
  return lat >= 51 && lat <= 56 && lng >= -11 && lng <= -5 ? v : null;
}

export function parseFilters(params: URLSearchParams): Filters {
  const type = params.get("type") as SaleType;
  const conf = params.get("minConfidence") as MinConfidence;
  const vat = params.get("vat") as Vat;
  const date = (k: string) => {
    const v = params.get(k);
    return v && isCalendarDate(v) ? v : null;
  };
  const point = near(params.get("near"));
  return {
    priceMin: num(params.get("priceMin")),
    priceMax: num(params.get("priceMax")),
    dateFrom: date("dateFrom"),
    dateTo: date("dateTo"),
    type: TYPES.includes(type) ? type : "any",
    excludeNonMarket: params.get("excludeNonMarket") !== "false",
    excludeBulk: params.get("excludeBulk") !== "false",
    minConfidence: CONFIDENCES.includes(conf) ? conf : "locality",
    vat: VATS.includes(vat) ? vat : "any",
    county: list(params.get("county")?.toLowerCase() ?? null, (c) =>
      (COUNTIES as readonly string[]).includes(c),
    ),
    area: list(params.get("area"), (s) => SLUG.test(s)),
    routingKey: list(params.get("routingKey")?.toUpperCase() ?? null, (k) => ROUTING_KEY.test(k)),
    near: point,
    radiusM: point ? num(params.get("radiusM"), 100, 20000) : null,
    maxStopM: num(params.get("maxStopM"), 50, 10000),
    maxSchoolM: num(params.get("maxSchoolM"), 50, 10000),
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
  if (f.vat !== "any") p.set("vat", f.vat);
  if (f.county.length) p.set("county", f.county.join(","));
  if (f.area.length) p.set("area", f.area.join(","));
  if (f.routingKey.length) p.set("routingKey", f.routingKey.join(","));
  if (f.near) {
    p.set("near", f.near);
    if (f.radiusM !== null) p.set("radiusM", String(f.radiusM));
  }
  if (f.maxStopM !== null) p.set("maxStopM", String(f.maxStopM));
  if (f.maxSchoolM !== null) p.set("maxSchoolM", String(f.maxSchoolM));
  return p;
}

export function parseSort(params: URLSearchParams): Sort {
  const sort = params.get("sort") as Sort;
  return SORTS.includes(sort) ? sort : "-date";
}

/** Place filters narrow where to look; the others narrow which sales. */
export function hasPlaceFilter(f: Filters): boolean {
  return f.county.length > 0 || f.area.length > 0 || f.routingKey.length > 0 || f.near !== null;
}

/** "53.34123,-6.26012" with five decimals: about a metre. */
export function formatNear(lat: number, lng: number): string {
  return `${lat.toFixed(5)},${lng.toFixed(5)}`;
}

export function countyName(code: string): string {
  return code.charAt(0).toUpperCase() + code.slice(1);
}

export type Box = [west: number, south: number, east: number, north: number];

/** A west,south,east,north box from the API (or its comma-joined form), if well formed. */
export function toBox(value: readonly number[] | string | null | undefined): Box | null {
  if (value === null || value === undefined) return null;
  const v = typeof value === "string" ? value.split(",").map(Number) : value;
  if (v.length !== 4 || !v.every(Number.isFinite)) return null;
  return [v[0] as number, v[1] as number, v[2] as number, v[3] as number];
}
