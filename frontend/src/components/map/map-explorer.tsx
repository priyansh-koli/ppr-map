"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import type {
  Map as MapLibreMap,
  MapGeoJSONFeature,
  MapMouseEvent,
  VectorTileSource,
} from "maplibre-gl";
import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError, STATIC_PREVIEW, type PropertyList } from "@/lib/api/client";
import { DEFAULT_FILTERS, type Filters, filtersToParams, parseFilters } from "@/lib/filters";

import { basemapStyle, IRELAND_BOUNDS, IRELAND_CENTER } from "./basemap";
import { placeCard } from "./card-position";
import { FilterPanel } from "./filter-panel";
import { type CardContent, HoverCard } from "./hover-card";
import {
  addDataLayers,
  distinctSales,
  INTERACTIVE_LAYERS,
  POINT_ZOOM,
  type SalePoint,
  type Selection,
  setLayerVisibility,
  showSelection,
  tileUrl,
} from "./layers";
import { Legend } from "./legend";
import { SalesList } from "./sales-list";

const LIST_ZOOM = 12;
const HOVER_DELAY_MS = 150;
// Pixels round the pointer that count as on a marker: small dots stay easy to hit.
const HOVER_SLOP = 3;
const CLICK_SLOP = 6;
// The API's answer for a box too large to list (/api/v1/properties).
const ZOOM_IN = "Zoom in to list sales";

/** The card, and the point on the map it belongs to (it follows that point as the map moves). */
type Card = { content: CardContent; anchor?: [number, number]; pinned: boolean } | null;
export type ListState =
  | { status: "zoom" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ok"; data: PropertyList };

function readView(): { center: [number, number]; zoom: number } {
  const p = new URLSearchParams(window.location.search);
  const lat = Number(p.get("lat"));
  const lng = Number(p.get("lng"));
  const z = Number(p.get("z"));
  if (p.has("lat") && p.has("lng") && Number.isFinite(lat) && Number.isFinite(lng)) {
    return { center: [lng, lat], zoom: Number.isFinite(z) && p.has("z") ? z : 13 };
  }
  return { center: IRELAND_CENTER, zoom: 6.3 };
}

function writeUrl(map: MapLibreMap, filters: Filters, hexes: boolean) {
  const p = filtersToParams(filters);
  const c = map.getCenter();
  p.set("lat", c.lat.toFixed(5));
  p.set("lng", c.lng.toFixed(5));
  p.set("z", map.getZoom().toFixed(2));
  if (hexes) p.set("layer", "hexes");
  // Keep Next's own history state: its patched replaceState then only changes the address and
  // does not dispatch a router update. That update would replace a navigation in flight, so a
  // link clicked while the map is still easing (moveend comes after) would go nowhere. The map
  // reads its view from window.location, never from useSearchParams, so nothing needs it.
  window.history.replaceState(
    window.history.state,
    "",
    `${window.location.pathname}?${p.toString()}`,
  );
}

const pointOf = (f: MapGeoJSONFeature): [number, number] | undefined =>
  f.geometry.type === "Point" ? (f.geometry.coordinates as [number, number]) : undefined;

function groupCard(f: MapGeoJSONFeature): CardContent {
  const p = f.properties;
  return f.layer.id === "stacks"
    ? { kind: "stack", n: Number(p.n), median: Number(p.median), confidence: String(p.confidence) }
    : { kind: "cell", n: Number(p.n), median: Number(p.median) };
}

/** What is under the pointer: sales win over the groups drawn at the same zoom. */
function hitsAt(map: MapLibreMap, e: MapMouseEvent, slop: number) {
  const { x, y } = e.point;
  const features = map.queryRenderedFeatures(
    [
      [x - slop, y - slop],
      [x + slop, y + slop],
    ],
    { layers: INTERACTIVE_LAYERS },
  );
  const sales = distinctSales(features);
  const group = features.find((f) => f.layer.id === "stacks" || f.layer.id === "cells");
  return { sales, group };
}

export function MapExplorer() {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [ready, setReady] = useState(false);
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [showHexes, setShowHexes] = useState(false);
  const [card, setCard] = useState<Card>(null);
  const [anchorPx, setAnchorPx] = useState<{ x: number; y: number } | null>(null);
  const [selected, setSelected] = useState<Selection | null>(null);
  const [list, setList] = useState<ListState>({ status: "zoom" });
  const [mapError, setMapError] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const highlighted = useRef<string | null>(null);
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  // What the pointer was last over, so the card only changes when that does.
  const hoverKey = useRef("");
  const pinned = useRef(false);
  const anchor = useRef<[number, number] | undefined>(undefined);
  const version = useRef("");
  const listRequest = useRef<AbortController | null>(null);
  const spotRequest = useRef<AbortController | null>(null);
  // Map event handlers are registered once; they read the current filters from here.
  const state = useRef({ filters, showHexes });
  useEffect(() => {
    state.current = { filters, showHexes };
  }, [filters, showHexes]);

  const showCard = useCallback((next: Card) => {
    anchor.current = next?.anchor;
    const map = mapRef.current;
    setAnchorPx(map && next?.anchor ? map.project(next.anchor) : null);
    setCard(next);
  }, []);

  /** Opens a property's details; pinning it also selects it on the map and in the list. */
  const openProperty = useCallback(
    (id: string, at?: [number, number], pin = false, price?: number) => {
      pinned.current = pin || pinned.current;
      if (pin && at) setSelected({ id, lngLat: at, price });
      showCard({
        content: { kind: "property", id, summary: null },
        anchor: at,
        pinned: pinned.current,
      });
      const settle = (content: CardContent) =>
        setCard((c) =>
          c?.content.kind === "property" && c.content.id === id ? { ...c, content } : c,
        );
      api
        .summary(id)
        .then((summary) => settle({ kind: "property", id, summary }))
        .catch((e: unknown) =>
          settle({
            kind: "property",
            id,
            summary: null,
            error:
              e instanceof ApiError && e.status === 404
                ? "No details for this sale."
                : "Details could not be loaded.",
          }),
        );
    },
    [showCard],
  );

  /** Several sales on one spot: pin a chooser and look up their addresses in the list API. */
  const openSpot = useCallback(
    (sales: SalePoint[]) => {
      pinned.current = true;
      setSelected(null);
      showCard({
        content: { kind: "spot", sales, addresses: null },
        anchor: sales[0]?.lngLat,
        pinned: true,
      });
      const lngs = sales.map((s) => s.lngLat[0]);
      const lats = sales.map((s) => s.lngLat[1]);
      const pad = 0.0003; // about 25 m: the dots overlap on screen, not always on the ground
      const query = filtersToParams(state.current.filters);
      query.set(
        "bbox",
        [
          Math.min(...lngs) - pad,
          Math.min(...lats) - pad,
          Math.max(...lngs) + pad,
          Math.max(...lats) + pad,
        ]
          .map((v) => v.toFixed(5))
          .join(","),
      );
      query.set("pageSize", "100");
      spotRequest.current?.abort();
      const request = new AbortController();
      spotRequest.current = request;
      const settle = (addresses: Record<string, string>) =>
        setCard((c) =>
          c?.content.kind === "spot" && c.content.sales === sales
            ? { ...c, content: { ...c.content, addresses } }
            : c,
        );
      api
        .list(query, { signal: request.signal })
        .then((data) => settle(Object.fromEntries(data.items.map((i) => [i.id, i.address]))))
        .catch(() => {
          if (!request.signal.aborted) settle({});
        });
    },
    [showCard],
  );

  const closeCard = useCallback(() => {
    pinned.current = false;
    hoverKey.current = "";
    spotRequest.current?.abort();
    setSelected(null);
    showCard(null);
  }, [showCard]);

  const highlight = useCallback((id: string | null) => {
    const map = mapRef.current;
    if (!map || !map.getSource("sales") || highlighted.current === id) return;
    if (highlighted.current) {
      map.setFeatureState(
        { source: "sales", sourceLayer: "sales", id: highlighted.current },
        { highlight: false },
      );
    }
    highlighted.current = id;
    if (id) map.setFeatureState({ source: "sales", sourceLayer: "sales", id }, { highlight: true });
  }, []);

  const refreshList = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;
    if (map.getZoom() < LIST_ZOOM) {
      setList({ status: "zoom" });
      return;
    }
    const b = map.getBounds();
    const query = filtersToParams(state.current.filters);
    query.set(
      "bbox",
      [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((v) => v.toFixed(5)).join(","),
    );
    query.set("pageSize", "50");
    // Only the latest view counts: a slower answer for where the map was must not replace it.
    listRequest.current?.abort();
    const request = new AbortController();
    listRequest.current = request;
    setList({ status: "loading" });
    api
      .list(query, { signal: request.signal })
      .then((data) => {
        if (!request.signal.aborted) setList({ status: "ok", data });
      })
      .catch((e: unknown) => {
        if (request.signal.aborted) return;
        setList(
          e instanceof ApiError && e.status === 422 && e.detail === ZOOM_IN
            ? { status: "zoom" }
            : { status: "error", message: "The list could not be loaded." },
        );
      });
  }, []);

  // Map set-up, once. MapLibre and PMTiles are loaded in the browser only.
  useEffect(() => {
    if (STATIC_PREVIEW || !container.current) return;
    let map: MapLibreMap | undefined;
    let cancelled = false;
    const initial = parseFilters(new URLSearchParams(window.location.search));
    const hexesInitially = new URLSearchParams(window.location.search).get("layer") === "hexes";
    setFilters(initial);
    setShowHexes(hexesInitially);
    (async () => {
      const maplibregl = await import("maplibre-gl");
      const { Protocol } = await import("pmtiles");
      if (cancelled || !container.current) return;
      // See scripts/copy-maplibre-worker.mjs.
      maplibregl.setWorkerUrl(`/maplibre/${maplibregl.getVersion()}/maplibre-gl-worker.mjs`);
      const protocol = new Protocol();
      maplibregl.addProtocol("pmtiles", protocol.tile);
      version.current = (await api.meta().catch(() => null))?.dataVersion ?? "";
      if (cancelled || !container.current) return;
      const view = readView();
      map = new maplibregl.Map({
        container: container.current,
        style: basemapStyle(window.location.origin),
        center: view.center,
        zoom: view.zoom,
        maxBounds: IRELAND_BOUNDS,
        attributionControl: { compact: true },
      });
      mapRef.current = map;
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      map.on("error", (e) => {
        if (String(e.error?.message ?? "").includes("/api/v1/tiles")) {
          setMapError("Sales could not be loaded. Is the data server running?");
        }
      });
      const measure = () => {
        if (map) setSize({ w: map.getContainer().clientWidth, h: map.getContainer().clientHeight });
      };
      map.on("resize", measure);
      map.on("load", () => {
        if (!map) return;
        measure();
        addDataLayers(map, filtersToParams(initial), version.current);
        setLayerVisibility(map, hexesInitially);
        setReady(true);
        refreshList();
      });
      // The card follows its point while the map pans and zooms.
      map.on("move", () => {
        if (map && anchor.current) setAnchorPx(map.project(anchor.current));
      });
      map.on("moveend", () => {
        if (!map) return;
        writeUrl(map, state.current.filters, state.current.showHexes);
        refreshList();
      });

      map.on("mousemove", (e) => {
        if (!map) return;
        const { sales, group } = hitsAt(map, e, HOVER_SLOP);
        map.getCanvas().style.cursor = sales.length || group ? "pointer" : "";
        const key = sales.length
          ? `sales:${sales.map((s) => s.id).join()}`
          : group
            ? `${group.layer.id}:${pointOf(group)?.join()}`
            : "";
        if (key === hoverKey.current) return;
        hoverKey.current = key;
        highlight(sales[0]?.id ?? null);
        clearTimeout(hoverTimer.current);
        if (pinned.current) return;
        if (!key) {
          showCard(null);
          return;
        }
        const [first] = sales;
        hoverTimer.current = setTimeout(() => {
          if (first && sales.length === 1) openProperty(first.id, first.lngLat);
          else if (first)
            showCard({
              content: { kind: "spot", sales, addresses: null },
              anchor: first.lngLat,
              pinned: false,
            });
          else if (group)
            showCard({ content: groupCard(group), anchor: pointOf(group), pinned: false });
        }, HOVER_DELAY_MS);
      });
      map.on("mouseout", () => {
        clearTimeout(hoverTimer.current);
        hoverKey.current = "";
        highlight(null);
        if (!pinned.current) showCard(null);
      });

      map.on("click", (e) => {
        if (!map) return;
        clearTimeout(hoverTimer.current);
        const { sales, group } = hitsAt(map, e, CLICK_SLOP);
        const [sale] = sales;
        if (sale && sales.length === 1) {
          pinned.current = true;
          openProperty(sale.id, sale.lngLat, true, sale.price);
        } else if (sales.length > 1) {
          openSpot(sales);
        } else if (group?.layer.id === "cells") {
          // A group of sales zoomed out: go to it, towards where its sales are drawn one by one.
          closeCard();
          const at = pointOf(group);
          if (at) map.easeTo({ center: at, zoom: Math.min(map.getZoom() + 3, POINT_ZOOM + 0.5) });
        } else if (group) {
          pinned.current = true;
          setSelected(null);
          showCard({ content: groupCard(group), anchor: pointOf(group), pinned: true });
        } else {
          closeCard();
        }
      });
    })().catch(() => setMapError("The map could not be started in this browser."));
    return () => {
      cancelled = true;
      clearTimeout(hoverTimer.current);
      listRequest.current?.abort();
      spotRequest.current?.abort();
      map?.remove();
      mapRef.current = null;
      import("maplibre-gl").then((m) => m.removeProtocol("pmtiles")).catch(() => {});
    };
  }, [openProperty, openSpot, closeCard, highlight, showCard, refreshList]);

  // Filters and layer choice: new tile URLs, the list, and the address bar.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource("sales") as VectorTileSource).setTiles([
      tileUrl("sales", filtersToParams(filters), version.current),
    ]);
    setLayerVisibility(map, showHexes);
    writeUrl(map, filters, showHexes);
    refreshList();
  }, [filters, showHexes, ready, refreshList]);

  useEffect(() => {
    const map = mapRef.current;
    if (map && ready) showSelection(map, selected);
  }, [selected, ready]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && closeCard();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [closeCard]);

  const locate = () => {
    if (!navigator.geolocation) {
      setMapError("This browser cannot share your location.");
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false);
        mapRef.current?.flyTo({ center: [pos.coords.longitude, pos.coords.latitude], zoom: 15 });
      },
      () => {
        setLocating(false);
        setMapError("Your location was not shared.");
      },
      { timeout: 10_000 },
    );
  };

  if (STATIC_PREVIEW) {
    return (
      <p className="mx-auto max-w-3xl px-4 py-10 text-muted">
        The live map needs the data server, which this static preview does not have. Run the app
        locally (<code>make up</code>) to explore every sale.
      </p>
    );
  }

  const cardPosition = placeCard(anchorPx, size);

  return (
    <div className="flex h-[calc(100dvh-3.5rem)] min-h-[32rem] flex-col md:flex-row md:gap-3 md:p-3">
      <aside className="order-2 max-h-[45vh] w-full shrink-0 overflow-y-auto border-t border-line bg-surface p-4 md:order-1 md:max-h-none md:w-80 md:rounded-[14px] md:border-t-0 md:shadow-window md:outline md:outline-1 md:-outline-offset-1 md:outline-line">
        <div className="space-y-6">
          <FilterPanel
            filters={filters}
            onChange={setFilters}
            showHexes={showHexes}
            onShowHexes={setShowHexes}
          />
          <Legend showHexes={showHexes} />
          <SalesList
            state={list}
            selectedId={selected?.id}
            onFocusItem={(id) => highlight(id)}
            onOpenItem={(id) => {
              const item =
                list.status === "ok" ? list.data.items.find((i) => i.id === id) : undefined;
              const map = mapRef.current;
              const at: [number, number] | undefined = item ? [item.lng, item.lat] : undefined;
              highlight(id);
              if (item && map) {
                // Zoom in far enough to see the sale on its own, not inside a group.
                map.easeTo({ center: at, zoom: Math.max(map.getZoom(), POINT_ZOOM + 1) });
              }
              pinned.current = true;
              openProperty(id, at, true, item?.latestSale.priceEur);
            }}
          />
        </div>
      </aside>
      <div className="relative order-1 min-h-[20rem] flex-1 overflow-hidden md:order-2 md:rounded-[14px] md:shadow-window md:outline md:outline-1 md:-outline-offset-1 md:outline-line">
        <div
          ref={container}
          className="h-full w-full"
          aria-label="Map of property sales"
          role="region"
        />
        <button
          type="button"
          onClick={locate}
          disabled={locating}
          className="btn btn-secondary btn-sm absolute left-3 top-3 shadow-window"
        >
          {locating ? "Finding you…" : "Near me"}
        </button>
        {mapError ? (
          <p
            role="alert"
            className="window absolute left-3 top-14 max-w-xs px-3 py-2 text-sm text-ink"
          >
            {mapError}
          </p>
        ) : null}
        {card ? (
          <div
            className="absolute z-10"
            style={cardPosition ?? { left: 12, bottom: 32 }}
            role="dialog"
            aria-label="Sale details"
            aria-live="polite"
          >
            <HoverCard
              content={card.content}
              onClose={card.pinned ? closeCard : undefined}
              onChoose={
                card.pinned
                  ? (sale) => openProperty(sale.id, sale.lngLat, true, sale.price)
                  : undefined
              }
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}
