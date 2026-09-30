/** Pure helpers shared by the search page, the home hero and saved searches. */
import type { Suggestion } from "./api/client";
import { DEFAULT_FILTERS, type Filters, toBox } from "./filters";
import { ROUTES } from "./routes";

/** A place picked in the search box, as a filter; a property opens its page instead. */
export function withSuggestion(f: Filters, s: Suggestion): Filters | null {
  const add = (xs: string[], x: string) => (xs.includes(x) ? xs : [...xs, x]);
  if (s.kind === "county" && s.slug) return { ...f, county: add(f.county, s.slug) };
  if (s.kind === "routing_key" && s.routingKey)
    return { ...f, routingKey: add(f.routingKey, s.routingKey) };
  if (s.kind !== "property" && s.slug) return { ...f, area: add(f.area, s.slug) };
  return null;
}

/** The same places with every other filter back at its default. */
export function placesOnly(f: Filters): Filters {
  const { county, area, routingKey, near, radiusM } = f;
  return { ...DEFAULT_FILTERS, county, area, routingKey, near, radiusM };
}

/** The map explorer at the results: centre of their box, at a zoom that shows it. */
export function mapHref(query: URLSearchParams, bbox: number[] | null): string {
  const p = new URLSearchParams(query);
  p.delete("sort");
  p.delete("page");
  p.delete("nearSource");
  const box = toBox(bbox);
  if (box) {
    const [w, s, e, n] = box;
    const span = Math.max(e - w, (n - s) * 1.6, 0.002);
    p.set("lat", ((s + n) / 2).toFixed(5));
    p.set("lng", ((w + e) / 2).toFixed(5));
    p.set("z", Math.min(16, Math.max(6, Math.log2(360 / span) - 0.5)).toFixed(2));
  }
  return `${ROUTES.map.path}?${p.toString()}`;
}
