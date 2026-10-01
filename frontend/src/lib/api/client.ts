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
export type Me = components["schemas"]["Me"];
export type Profile = components["schemas"]["Profile-Output"];
export type ProfileInput = components["schemas"]["Profile-Input"];
export type Policies = components["schemas"]["Policies"];
export type RegisterIn = components["schemas"]["RegisterIn"];
export type WishlistItem = components["schemas"]["WishlistItemOut"];
export type View = components["schemas"]["ViewOut"];
export type MePatch = components["schemas"]["MePatch"];
export type Overview = components["schemas"]["Overview"];
export type SearchResults = components["schemas"]["SearchResults"];
export type Suggestion = components["schemas"]["Suggestion"];
export type SearchHistoryItem = components["schemas"]["SearchHistoryOut"];
export type ViewPage = components["schemas"]["Page_ViewOut_"];
export type SearchHistoryPage = components["schemas"]["Page_SearchHistoryOut_"];
export type AreaRef = components["schemas"]["AreaRef"];
export type Rules = components["schemas"]["Rules"];
export type SavedSearch = components["schemas"]["SavedSearchOut"];
export type ReportIn = components["schemas"]["ReportIn"];
export type AdminOverview = components["schemas"]["AdminOverview"];
export type IngestRun = components["schemas"]["IngestRunOut"];
export type IngestRunDetail = components["schemas"]["IngestRunDetail"];
export type AdminJob = components["schemas"]["Job"];
export type QueueItem = components["schemas"]["QueueItem"];
export type GeocodeFix = components["schemas"]["GeocodeFix"];
export type GeocodeFixed = components["schemas"]["GeocodeFixed"];
export type RemovalRequest = components["schemas"]["RemovalOut"];
export type AdminUser = components["schemas"]["AdminUser"];
export type AuditEntry = components["schemas"]["AuditEntry"];
export interface PageOf<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}
export type AlertFrequency = SavedSearch["alertFrequency"];
export type AreaDetail = components["schemas"]["AreaDetail"];
export type AreaStats = components["schemas"]["AreaStatsOut"];
export type SeriesPoint = components["schemas"]["SeriesPoint"];
export type Distribution = components["schemas"]["Distribution"];
export type StampDuty = components["schemas"]["StampDutyOut"];
export type Affordability = components["schemas"]["AffordabilityOut"];
export type CountyStat = components["schemas"]["CountyStat"];
export type PriceEstimate = components["schemas"]["PriceEstimate"];
export type Comparables = components["schemas"]["Comparables"];
export type Sources = components["schemas"]["Sources"];
export type SourceInfo = components["schemas"]["SourceOut"];

/** The GitHub Pages preview (D-034) is static: there is no API or tile server behind it. */
export const STATIC_PREVIEW = process.env.NEXT_PUBLIC_STATIC_PREVIEW === "1";

/** One entry of a 422 problem's `errors` (FastAPI request validation). */
export interface ValidationIssue {
  loc: (string | number)[];
  msg: string;
  type: string;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
    readonly errors: ValidationIssue[] = [],
  ) {
    super(detail);
  }

  /** The request field the first validation error names ("password"), if any. */
  get field(): string | null {
    const loc = this.errors[0]?.loc ?? [];
    const last = loc[loc.length - 1];
    return loc.length > 1 && typeof last === "string" ? last : null;
  }
}

/** Fired on `window` when an authenticated call gets a 401, so the session can re-check. */
export const UNAUTHORIZED_EVENT = "ppr:unauthorized";

interface Problem {
  title?: string;
  detail?: string;
  errors?: ValidationIssue[];
}

/** Validation problems have no `detail`; name the first failing field instead. */
function problemMessage(body: Problem, fallback: string): string {
  if (body.detail) return body.detail;
  const first = Array.isArray(body.errors) ? body.errors[0] : undefined;
  if (first?.msg) {
    // loc starts with where the value was ("body", "query"); the rest names the field.
    const field = (first.loc ?? []).slice(1).join(".");
    return field ? `${field}: ${first.msg}` : first.msg;
  }
  return body.title ?? fallback;
}

/** In the browser the API is on the same origin (Caddy, D-026); on the server, call it directly. */
function base(): string {
  if (typeof window !== "undefined") return "";
  return process.env.INTERNAL_API_ORIGIN || "http://localhost:8000";
}

const CSRF_COOKIE = "ppr_csrf";

/** The CSRF cookie the API sets on every response, echoed in a header (D-008). */
function csrfToken(): string {
  if (typeof document === "undefined") return "";
  const match = document.cookie.match(new RegExp(`(?:^|; )${CSRF_COOKIE}=([^;]*)`));
  return match?.[1] ? decodeURIComponent(match[1]) : "";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (method !== "GET") {
    if (!csrfToken()) await fetch(`${base()}/api/v1/auth/policies`, { credentials: "same-origin" });
    headers.set("X-CSRF-Token", csrfToken());
    if (init.body !== undefined) headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`${base()}/api/v1${path}`, {
    credentials: "same-origin",
    ...init,
    headers,
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as Problem;
    // Checking the session or signing in answers 401 by design; anything else means it ended.
    const quiet = path === "/me" && method === "GET";
    if (res.status === 401 && !quiet && path !== "/auth/login" && typeof window !== "undefined") {
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
    throw new ApiError(
      res.status,
      problemMessage(body, res.statusText),
      Array.isArray(body.errors) ? body.errors : [],
    );
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const get = <T>(path: string, init?: RequestInit) => request<T>(path, init);
const send = <T>(method: string, path: string, body?: unknown) =>
  request<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });

type Accepted = components["schemas"]["Accepted"];

export const api = {
  meta: (init?: RequestInit) => get<Meta>("/meta", init),
  sources: (init?: RequestInit) => get<Sources>("/sources", init),
  overview: (init?: RequestInit) => get<Overview>("/stats/overview", init),
  summary: (id: string, init?: RequestInit) =>
    get<PropertySummary>(`/properties/${encodeURIComponent(id)}/summary`, init),
  list: (query: URLSearchParams, init?: RequestInit) =>
    get<PropertyList>(`/properties?${query.toString()}`, init),
  property: (id: string, init?: RequestInit) =>
    get<PropertyDetail>(`/properties/${encodeURIComponent(id)}`, init),
  estimate: (id: string, init?: RequestInit) =>
    get<PriceEstimate>(`/properties/${encodeURIComponent(id)}/estimate`, init),
  comparables: (id: string, init?: RequestInit) =>
    get<Comparables>(`/properties/${encodeURIComponent(id)}/comparables`, init),

  policies: () => get<Policies>("/auth/policies"),
  register: (body: RegisterIn) => send<Accepted>("POST", "/auth/register", body),
  verifyEmail: (token: string) => send<Accepted>("POST", "/auth/verify-email", { token }),
  resendVerification: () => send<Accepted>("POST", "/auth/resend-verification"),
  login: (email: string, password: string) => send<Me>("POST", "/auth/login", { email, password }),
  logout: () => send<void>("POST", "/auth/logout"),
  logoutAll: () => send<void>("POST", "/auth/logout-all"),
  forgotPassword: (email: string) => send<Accepted>("POST", "/auth/forgot-password", { email }),
  resetPassword: (token: string, password: string) =>
    send<Accepted>("POST", "/auth/reset-password", { token, password }),

  me: () => get<Me>("/me"),
  updateMe: (body: MePatch) => send<Me>("PATCH", "/me", body),
  changePassword: (currentPassword: string, newPassword: string) =>
    send<void>("POST", "/me/password", { currentPassword, newPassword }),
  deleteMe: (password: string) => send<void>("DELETE", "/me", { password }),

  wishlist: () => get<WishlistItem[]>("/me/wishlist"),
  saveArea: (areaSlug: string, note?: string) =>
    send<WishlistItem>("POST", "/me/wishlist", { areaSlug, note }),
  saveProperty: (propertyId: string, note?: string) =>
    send<WishlistItem>("POST", "/me/wishlist", { propertyId, note }),
  noteWishlistItem: (id: number, note: string | null) =>
    send<WishlistItem>("PATCH", `/me/wishlist/${id}`, { note }),
  removeWishlistItem: (id: number) => send<void>("DELETE", `/me/wishlist/${id}`),
  compare: (ids: string[], init?: RequestInit) =>
    get<PropertySummary[]>(
      `/me/wishlist/compare?ids=${ids.map(encodeURIComponent).join(",")}`,
      init,
    ),

  search: (query: URLSearchParams, init?: RequestInit) =>
    get<SearchResults>(`/search?${query.toString()}`, init),
  autocomplete: (q: string, init?: RequestInit) =>
    get<Suggestion[]>(`/geocode/autocomplete?q=${encodeURIComponent(q)}`, init),

  area: (slug: string, init?: RequestInit) =>
    get<AreaDetail>(`/areas/${encodeURIComponent(slug)}`, init),
  areaStats: (slug: string, query: URLSearchParams, init?: RequestInit) =>
    get<AreaStats>(`/areas/${encodeURIComponent(slug)}/stats?${query.toString()}`, init),
  areaDistribution: (slug: string, init?: RequestInit) =>
    get<Distribution>(`/areas/${encodeURIComponent(slug)}/distribution`, init),

  savedSearches: () => get<SavedSearch[]>("/me/saved-searches"),
  saveSearch: (name: string, query: Record<string, string>, alertFrequency: AlertFrequency) =>
    send<SavedSearch>("POST", "/me/saved-searches", { name, query, alertFrequency }),
  updateSavedSearch: (
    id: string,
    body: { name?: string; query?: Record<string, string>; alertFrequency?: AlertFrequency },
  ) => send<SavedSearch>("PATCH", `/me/saved-searches/${id}`, body),
  deleteSavedSearch: (id: string) => send<void>("DELETE", `/me/saved-searches/${id}`),
  savedSearchCsvUrl: (id: string) => `/api/v1/me/saved-searches/${id}/export.csv`,
  unsubscribe: (token: string) => send<{ name: string }>("POST", "/alerts/unsubscribe", { token }),

  report: (body: ReportIn) => send<{ reference: string }>("POST", "/reports", body),

  admin: {
    overview: () => get<AdminOverview>("/admin/overview"),
    runs: (page = 1, kind?: string) =>
      get<PageOf<IngestRun>>(`/admin/ingest-runs?page=${page}${kind ? `&kind=${kind}` : ""}`),
    run: (id: number) => get<IngestRunDetail>(`/admin/ingest-runs/${id}`),
    startRun: (step: string) => send<AdminJob>("POST", "/admin/ingest-runs", { step }),
    jobs: () => get<AdminJob[]>("/admin/jobs"),
    geocodeQueue: (kind: string, page = 1, county?: string) =>
      get<PageOf<QueueItem>>(
        `/admin/geocode/queue?kind=${kind}&page=${page}${county ? `&county=${county}` : ""}`,
      ),
    fixGeocode: (id: string, body: GeocodeFix) =>
      send<GeocodeFixed>("PUT", `/admin/properties/${encodeURIComponent(id)}/geocode`, body),
    removals: (status: string, page = 1) =>
      get<PageOf<RemovalRequest>>(`/admin/removal-requests?status=${status}&page=${page}`),
    decide: (id: string, status: string, decisionNote?: string) =>
      send<RemovalRequest>("PATCH", `/admin/removal-requests/${id}`, { status, decisionNote }),
    users: (q: string, page = 1) =>
      get<PageOf<AdminUser>>(`/admin/users?page=${page}${q ? `&q=${encodeURIComponent(q)}` : ""}`),
    changeUser: (id: string, body: { isActive?: boolean; roles?: string[]; password?: string }) =>
      send<AdminUser>("PATCH", `/admin/users/${id}`, body),
    audit: (page = 1, filters: Record<string, string> = {}) =>
      get<PageOf<AuditEntry>>(
        `/admin/audit-log?${new URLSearchParams({ ...filters, page: String(page) }).toString()}`,
      ),
  },

  rules: (init?: RequestInit) => get<Rules>("/tools/rules", init),
  stampDuty: (query: URLSearchParams, init?: RequestInit) =>
    get<StampDuty>(`/tools/stamp-duty?${query.toString()}`, init),
  affordability: (query: URLSearchParams, init?: RequestInit) =>
    get<Affordability>(`/tools/affordability?${query.toString()}`, init),

  recordView: (propertyId: string) => send<void>("POST", "/me/history/views", { propertyId }),
  views: (page = 1) => get<ViewPage>(`/me/history/views?page=${page}`),
  recordSearch: (query: Record<string, string>, label?: string) =>
    send<void>("POST", "/me/history/searches", { query, label }),
  searches: (page = 1) => get<SearchHistoryPage>(`/me/history/searches?page=${page}`),
  clearSearches: () => send<void>("DELETE", "/me/history/searches"),
  deleteSearch: (id: number) => send<void>("DELETE", `/me/history/searches/${id}`),
  clearViews: () => send<void>("DELETE", "/me/history/views"),
  deleteView: (id: number) => send<void>("DELETE", `/me/history/views/${id}`),
};
