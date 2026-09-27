/**
 * Price bands for the map: one blue hue, light to dark, validated as an ordinal ramp against
 * the basemap's land colour (#e2dfda) with the dataviz palette checks: monotone lightness,
 * visible steps, and a light end that clears 2:1. Four steps is the most that passes there.
 */
export const PRICE_BANDS = [
  { max: 200_000, color: "#5598e7", label: "Under €200k" },
  { max: 350_000, color: "#2a78d6", label: "€200k–€350k" },
  { max: 550_000, color: "#1c5cab", label: "€350k–€550k" },
  { max: Infinity, color: "#0d366b", label: "€550k and over" },
] as const;

export const SUPPRESSED_COLOR = "#9a9690";

export function bandFor(price: number) {
  return PRICE_BANDS.find((b) => price < b.max) ?? PRICE_BANDS[3];
}

/** A MapLibre `step` expression colouring by the given numeric property. */
export function bandExpression(property: string): unknown[] {
  const [first, ...rest] = PRICE_BANDS;
  const expr: unknown[] = ["step", ["get", property], first.color];
  let lowerBound: number = first.max;
  for (const band of rest) {
    expr.push(lowerBound, band.color);
    lowerBound = band.max;
  }
  return expr;
}
