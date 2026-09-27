/**
 * Typed calls to `/api/v1`. Shapes come from the generated OpenAPI types
 * (`make api-types`), never written by hand.
 */
import type { components } from "./schema";

export type Meta = components["schemas"]["Meta"];
export type PropertySummary = components["schemas"]["PropertySummary"];
export type PropertyList = components["schemas"]["PropertyList"];
export type PropertyListItem = components["schemas"]["PropertyListItem"];
export type PropertyDetail = components["schemas"]["PropertyDetail"];
export type Confidence = PropertySummary["confidence"];

/** The GitHub Pages preview (D-034) is static: there is no API or tile server behind it. */
export const STATIC_PREVIEW = process.env.NEXT_PUBLIC_STATIC_PREVIEW === "1";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
  }
}

/** In the browser the API is on the same origin (Caddy, D-026); on the server, call it directly. */
function base(): string {
  if (typeof window !== "undefined") return "";
  return process.env.INTERNAL_API_ORIGIN || "http://localhost:8000";
}

async function get<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${base()}/api/v1${path}`, init);
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: string; title?: string };
    throw new ApiError(res.status, body.detail ?? body.title ?? res.statusText);
  }
  return (await res.json()) as T;
}

export const api = {
  meta: (init?: RequestInit) => get<Meta>("/meta", init),
  summary: (id: string, init?: RequestInit) =>
    get<PropertySummary>(`/properties/${encodeURIComponent(id)}/summary`, init),
  list: (query: URLSearchParams, init?: RequestInit) =>
    get<PropertyList>(`/properties?${query.toString()}`, init),
  property: (id: string, init?: RequestInit) =>
    get<PropertyDetail>(`/properties/${encodeURIComponent(id)}`, init),
};
