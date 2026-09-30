"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useSession } from "@/components/auth/session";
import { ConfidenceChip } from "@/components/ui/confidence-chip";
import { Window } from "@/components/ui/window";
import {
  api,
  ApiError,
  type PropertyListItem,
  type SearchResults,
  STATIC_PREVIEW,
} from "@/lib/api/client";
import { describeSearch, slugLabel } from "@/lib/describe";
import {
  countyName,
  type Filters,
  filtersToParams,
  formatNear,
  parseFilters,
  parseSort,
  type Sort,
} from "@/lib/filters";
import { formatDate, formatEur } from "@/lib/format";
import { ROUTES } from "@/lib/routes";

import { mapHref, placesOnly, withSuggestion } from "@/lib/search";

import { PlaceSearch } from "./place-search";
import { ResultsMap } from "./results-map";
import { SearchFilters } from "./search-filters";

const PAGE_SIZE = 25;
// A search counts as "run" once it has stayed the same this long (history, D-047).
const HISTORY_DELAY_MS = 2500;
const SORT_OPTIONS: [Sort, string][] = [
  ["-date", "Newest sale first"],
  ["date", "Oldest sale first"],
  ["-price", "Highest price first"],
  ["price", "Lowest price first"],
  ["-change", "Biggest rise since the previous sale"],
  ["change", "Biggest fall since the previous sale"],
];

/** The latest answer, and the query it answers: while `key` differs, a search is running. */
type Result = { key: string; data?: SearchResults; error?: string };

function Chip({
  children,
  onRemove,
  label,
}: {
  children: ReactNode;
  onRemove: () => void;
  label: string;
}) {
  return (
    <span className="chip gap-1.5 pr-1">
      {children}
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${label}`}
        className="grid h-5 w-5 place-items-center rounded-full hover:bg-fill"
      >
        <svg viewBox="0 0 10 10" className="h-2.5 w-2.5" aria-hidden="true">
          <path
            d="M2 2l6 6M8 2l-6 6"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
          />
        </svg>
      </button>
    </span>
  );
}

function ResultRow({
  item,
  onHover,
}: {
  item: PropertyListItem;
  onHover: (id: string | null) => void;
}) {
  const sale = item.latestSale;
  const flags = [
    sale.isNew ? "New" : "Second-hand",
    sale.flags.vatExclusive ? "filed without VAT" : null,
    sale.flags.notFullMarketPrice ? "not full market price" : null,
    sale.flags.bulk ? "bulk sale" : null,
  ].filter(Boolean);
  return (
    <li
      onMouseEnter={() => onHover(item.id)}
      onMouseLeave={() => onHover(null)}
      className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 px-4 py-3 hover:bg-surface-2"
    >
      <Link
        href={`/property/${item.id}`}
        className="min-w-0 font-medium text-ink underline decoration-line underline-offset-2 hover:decoration-ink"
        onFocus={() => onHover(item.id)}
        onBlur={() => onHover(null)}
      >
        {item.address}
      </Link>
      <span className="text-right font-semibold text-ink tabular-nums">
        {formatEur(sale.priceEur)}
      </span>
      <span className="text-xs text-muted">
        {formatDate(sale.date)} · {flags.join(" · ")}
        {item.nSales > 1 ? ` · ${item.nSales} sales on record` : ""}
      </span>
      <span className="justify-self-end">
        <ConfidenceChip confidence={item.confidence} />
      </span>
      {item.change ? (
        <span className="col-span-2 text-xs text-ink-2">
          <span className="font-semibold text-ink">
            {item.change.changePct >= 0 ? "+" : "−"}
            {Math.abs(item.change.changePct).toLocaleString("en-IE")}%
          </span>{" "}
          since {formatEur(item.change.previousPriceEur)} in {formatDate(item.change.previousDate)}
          <span className="text-muted"> (not adjusted for inflation or work done)</span>
        </span>
      ) : null}
    </li>
  );
}

export function SearchPage() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const { me } = useSession();
  const qs = params.toString();
  const filters = useMemo(() => parseFilters(new URLSearchParams(qs)), [qs]);
  const sort = useMemo(() => parseSort(new URLSearchParams(qs)), [qs]);
  const page = Math.max(1, Number(new URLSearchParams(qs).get("page")) || 1);
  const geolocated = new URLSearchParams(qs).get("nearSource") === "geolocation";
  const [result, setResult] = useState<Result>({ key: "" });
  const [version, setVersion] = useState("");
  const [hovered, setHovered] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);
  const [locateError, setLocateError] = useState<string | null>(null);
  const [names, setNames] = useState<Record<string, string>>({});
  const recorded = useRef("");

  const filterQuery = useMemo(() => filtersToParams(filters), [filters]);
  const apiQuery = useMemo(() => {
    const q = new URLSearchParams(filterQuery);
    if (sort !== "-date") q.set("sort", sort);
    if (page > 1) q.set("page", String(page));
    q.set("pageSize", String(PAGE_SIZE));
    return q;
  }, [filterQuery, sort, page]);
  const apiKey = apiQuery.toString();

  const go = useCallback(
    (next: Filters, nextSort: Sort = sort, options: { nearSource?: boolean } = {}) => {
      const q = filtersToParams(next);
      if (nextSort !== "-date") q.set("sort", nextSort);
      const keepSource = options.nearSource ?? (geolocated && next.near === filters.near);
      if (keepSource && next.near) q.set("nearSource", "geolocation");
      const s = q.toString();
      router.replace(`${pathname}${s ? `?${s}` : ""}`, { scroll: false });
    },
    [router, pathname, sort, geolocated, filters.near],
  );

  useEffect(() => {
    if (STATIC_PREVIEW) return;
    api
      .meta()
      .then((m) => setVersion(m.dataVersion))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (STATIC_PREVIEW) return;
    const request = new AbortController();
    api
      .search(new URLSearchParams(apiKey), { signal: request.signal })
      .then((data) => {
        if (request.signal.aborted) return;
        setResult({ key: apiKey, data });
        const places = (data.places ?? []).map((p) => [p.slug, p.name]);
        setNames((n) => ({ ...n, ...Object.fromEntries(places) }));
      })
      .catch((e: unknown) => {
        if (request.signal.aborted) return;
        setResult({
          key: apiKey,
          error:
            e instanceof ApiError && e.status === 429
              ? "Too many searches in a minute. Wait a moment and try again."
              : e instanceof ApiError && e.status === 422
                ? `These filters cannot be used: ${e.detail}`
                : "Search could not be loaded. Is the data server running?",
        });
      });
    return () => request.abort();
  }, [apiKey]);

  // History: a search the user settled on, once, and never with their location's coordinates.
  const historyKey = new URLSearchParams(filterQuery);
  if (sort !== "-date") historyKey.set("sort", sort);
  const historyQuery = historyKey.toString();
  useEffect(() => {
    if (!me?.historyEnabled || !historyQuery || recorded.current === historyQuery) return;
    const t = setTimeout(() => {
      recorded.current = historyQuery;
      const query = Object.fromEntries(new URLSearchParams(historyQuery));
      if (geolocated) query.nearSource = "geolocation";
      const label = filters.area.map((s) => names[s] ?? slugLabel(s)).join(", ") || undefined;
      api.recordSearch(query, label).catch(() => {});
    }, HISTORY_DELAY_MS);
    return () => clearTimeout(t);
  }, [me?.historyEnabled, historyQuery, geolocated, filters.area, names]);

  const locate = () => {
    setLocateError(null);
    if (!navigator.geolocation) {
      setLocateError("This browser cannot share your location.");
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false);
        go(
          {
            ...filters,
            near: formatNear(pos.coords.latitude, pos.coords.longitude),
            radiusM: filters.radiusM ?? 1000,
          },
          sort,
          { nearSource: true },
        );
      },
      () => {
        setLocating(false);
        setLocateError("Your location was not shared, so nothing changed.");
      },
      { timeout: 10_000 },
    );
  };

  if (STATIC_PREVIEW) {
    return (
      <p className="mx-auto max-w-3xl px-4 py-10 text-muted">
        Search needs the data server, which this static preview does not have. Run the app locally (
        <code>make up</code>) to search every sale.
      </p>
    );
  }

  const loading = result.key !== apiKey;
  // While a new search runs, the previous results stay on screen, marked as updating.
  const data = result.error ? undefined : result.data;
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const setPage = (p: number) => {
    const q = new URLSearchParams(qs);
    if (p > 1) q.set("page", String(p));
    else q.delete("page");
    router.replace(`${pathname}?${q.toString()}`, { scroll: false });
    document.getElementById("results-heading")?.scrollIntoView({ block: "start" });
  };
  const without = <K extends "county" | "area" | "routingKey">(key: K, value: string) =>
    go({ ...filters, [key]: filters[key].filter((x) => x !== value) });
  const hasPlaces =
    filters.county.length + filters.area.length + filters.routingKey.length > 0 || !!filters.near;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:py-10">
      <header className="max-w-3xl">
        <p className="eyebrow">Search the register</p>
        <h1 className="mt-2 font-display text-4xl font-semibold tracking-[-0.015em] text-ink sm:text-5xl">
          {ROUTES.search.title}
        </h1>
        <p className="mt-3 text-lg text-ink-2">
          Choose places, then narrow by price, date and more. The address bar always holds this
          search, so you can share it or come back to it.
        </p>
      </header>

      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-start">
        <div className="flex-1">
          <PlaceSearch
            size="lg"
            onSelect={(s) => {
              const next = withSuggestion(filters, s);
              if (next) {
                if (s.slug) setNames((n) => ({ ...n, [s.slug as string]: s.label }));
                go(next);
              } else if (s.propertyId) router.push(`/property/${s.propertyId}`);
            }}
          />
        </div>
        <div className="sm:w-60">
          <button
            type="button"
            onClick={locate}
            disabled={locating}
            className="btn btn-secondary w-full"
          >
            {locating ? "Finding you…" : "Near my location"}
          </button>
          <p className="mt-1 text-xs text-muted">
            Your browser asks first. The location is used for this search only; your history keeps
            &ldquo;near my location&rdquo;, not where you are.
          </p>
        </div>
      </div>
      {locateError ? (
        <p role="alert" className="mt-2 text-sm text-ink">
          {locateError}
        </p>
      ) : null}

      <div className="mt-4 flex flex-wrap items-center gap-2" aria-label="Places searched">
        {!hasPlaces ? <span className="text-sm text-muted">All of Ireland</span> : null}
        {filters.county.map((c) => (
          <Chip key={c} label={countyName(c)} onRemove={() => without("county", c)}>
            Co. {countyName(c)}
          </Chip>
        ))}
        {filters.area.map((a) => (
          <Chip key={a} label={names[a] ?? slugLabel(a)} onRemove={() => without("area", a)}>
            {names[a] ?? slugLabel(a)}
          </Chip>
        ))}
        {filters.routingKey.map((k) => (
          <Chip key={k} label={k} onRemove={() => without("routingKey", k)}>
            {k}
          </Chip>
        ))}
        {filters.near ? (
          <Chip
            label="the distance filter"
            onRemove={() => go({ ...filters, near: null, radiusM: null })}
          >
            Within {((filters.radiusM ?? 1000) / 1000).toLocaleString("en-IE")} km of{" "}
            {geolocated ? "your location" : "a point"}
          </Chip>
        ) : null}
        {qs ? (
          <button
            type="button"
            className="text-sm text-accent underline"
            onClick={() => router.replace(pathname, { scroll: false })}
          >
            Clear everything
          </button>
        ) : null}
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[18rem_1fr]">
        <Window as="aside" title="filters" bodyClassName="p-4">
          <SearchFilters filters={filters} onChange={(f) => go(f)} />
          {filtersToParams(placesOnly(filters)).toString() !== filterQuery.toString() ? (
            <button
              type="button"
              className="mt-4 text-sm text-accent underline"
              onClick={() => go(placesOnly(filters))}
            >
              Reset the filters (keep the places)
            </button>
          ) : null}
        </Window>

        <section aria-labelledby="results-heading" className="min-w-0 space-y-4">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 id="results-heading" className="font-display text-2xl text-ink">
                {data
                  ? `${data.total.toLocaleString("en-IE")} ${data.total === 1 ? "property" : "properties"}`
                  : "Searching…"}
              </h2>
              <p className="text-sm text-muted" aria-live="polite">
                {loading ? "Updating…" : describeSearch(Object.fromEntries(filterQuery), names)}
                {data ? " · each property once, with its latest matching sale" : ""}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <label className="text-sm">
                <span className="sr-only">Sort</span>
                <select
                  className="px-2.5 py-1.5"
                  value={sort}
                  onChange={(e) => go(filters, e.target.value as Sort)}
                >
                  {SORT_OPTIONS.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <Link
                href={mapHref(filterQuery, data?.bbox ?? null)}
                className="btn btn-secondary btn-sm"
              >
                Open on the map
              </Link>
            </div>
          </div>

          <div className="h-72 overflow-hidden rounded-[14px] shadow-window outline outline-1 -outline-offset-1 outline-line sm:h-80">
            <ResultsMap
              query={filterQuery}
              bbox={data?.bbox ?? null}
              circle={
                filters.near ? { near: filters.near, radiusM: filters.radiusM ?? 1000 } : null
              }
              version={version}
              highlightId={hovered}
              onOpen={(id) => router.push(`/property/${id}`)}
            />
          </div>

          {result.error && !loading ? (
            <p role="alert" className="window px-4 py-3">
              {result.error}
            </p>
          ) : null}
          {data && data.total === 0 ? (
            <div className="window px-4 py-5">
              <p className="font-medium text-ink">No sales match this search.</p>
              <p className="mt-1 text-sm text-muted">
                Try a wider price or date range, a larger distance, or include sales placed only at
                their town.
              </p>
            </div>
          ) : null}
          {data && data.items.length ? (
            <Window
              title={`results · page ${page} of ${pages.toLocaleString("en-IE")}`}
              bodyClassName="p-0"
            >
              <ol className="divide-y divide-line" aria-busy={loading}>
                {data.items.map((item) => (
                  <ResultRow key={item.id} item={item} onHover={setHovered} />
                ))}
              </ol>
            </Window>
          ) : null}
          {data && pages > 1 ? (
            <nav
              aria-label="Result pages"
              className="flex items-center justify-between gap-3 text-sm"
            >
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
              >
                Previous
              </button>
              <span className="text-muted">
                Page {page} of {pages.toLocaleString("en-IE")}
              </span>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={page >= Math.min(pages, 1000)}
                onClick={() => setPage(page + 1)}
              >
                Next
              </button>
            </nav>
          ) : null}
        </section>
      </div>
    </div>
  );
}
