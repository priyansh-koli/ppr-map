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

export const formatEur = (value: number) => EUR.format(value);
export const formatEurShort = (value: number) => EUR_SHORT.format(value);
/** ISO dates ("2026-09-18") read as calendar dates, not as local midnight. */
export const formatDate = (iso: string) => DATE.format(new Date(`${iso}T00:00:00Z`));
export const formatMonth = (iso: string) => MONTH.format(new Date(`${iso}T00:00:00Z`));

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
