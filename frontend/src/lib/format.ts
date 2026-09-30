const EUR = new Intl.NumberFormat("en-IE", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});
const EUR_SHORT = new Intl.NumberFormat("en-IE", {
  style: "currency",
  currency: "EUR",
  notation: "compact",
  maximumFractionDigits: 1,
});
const DATE_TIME = new Intl.DateTimeFormat("en-IE", { dateStyle: "medium", timeStyle: "short" });
const DATE = new Intl.DateTimeFormat("en-IE", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});
const MONTH = new Intl.DateTimeFormat("en-IE", {
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

// Money may arrive as a JSON number or as a decimal string ("350000.00"); both read the same.
export const formatEur = (value: number | string) => EUR.format(Number(value));
export const formatEurShort = (value: number | string) => EUR_SHORT.format(Number(value));
/** ISO dates ("2026-09-18") read as calendar dates, not as local midnight. */
export const formatDate = (iso: string) => DATE.format(new Date(`${iso}T00:00:00Z`));
export const formatMonth = (iso: string) => MONTH.format(new Date(`${iso}T00:00:00Z`));

/** An ISO timestamp in local time; anything unparseable is shown as it came. */
export function formatDateTime(iso: string): string {
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? iso : DATE_TIME.format(when);
}

export function formatDistance(metres: number): string {
  return metres < 1000 ? `${Math.round(metres / 10) * 10} m` : `${(metres / 1000).toFixed(1)} km`;
}

/** Tile dates are yyyymmdd integers. */
export function tileDate(yyyymmdd: number): string {
  const s = String(yyyymmdd);
  return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
}

export const CONFIDENCE_LABEL: Record<string, string> = {
  exact: "Exact address",
  street: "Street or estate",
  locality: "Town, village or townland",
  routing_key: "Eircode area",
  county: "County only",
  unmatched: "Not located",
};

export const CONFIDENCE_NOTE: Record<string, string> = {
  exact: "Matched to the house number on the map.",
  street: "Placed on its street or estate; the house itself is somewhere along it.",
  locality: "Only its town, village or townland could be found.",
  routing_key: "Placed at the typical location of its Eircode routing key.",
  county: "Only its county is known.",
  unmatched: "Could not be located.",
};

/** A rate held as a fraction: 0.135 → "13.5%", 0.09 → "9%". */
export function formatRate(fraction: number): string {
  return `${Number((fraction * 100).toFixed(2))}%`;
}

const EUR_CENTS = new Intl.NumberFormat("en-IE", {
  style: "currency",
  currency: "EUR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
/** Tax to the cent: €3,524.23. */
export const formatEurCents = (value: number | string) => EUR_CENTS.format(Number(value));
