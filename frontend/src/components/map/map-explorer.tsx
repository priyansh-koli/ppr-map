"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import type {
  ExpressionSpecification,
  Map as MapLibreMap,
  MapLayerMouseEvent,
  VectorTileSource,
} from "maplibre-gl";
import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError, STATIC_PREVIEW, type PropertyList } from "@/lib/api/client";
import { DEFAULT_FILTERS, type Filters, filtersToParams, parseFilters } from "@/lib/filters";
import { bandExpression, SUPPRESSED_COLOR } from "@/lib/price-bands";

import { basemapStyle, IRELAND_BOUNDS, IRELAND_CENTER } from "./basemap";
import { FilterPanel } from "./filter-panel";
import { type CardContent, HoverCard } from "./hover-card";
import { Legend } from "./legend";
import { SalesList } from "./sales-list";

const TILES = "/api/v1/tiles";
// Points are drawn from z14 (migration 0004); the list needs a box the API accepts.
const POINT_ZOOM = 14;
const LIST_ZOOM = 12;
const HOVER_DELAY_MS = 150;
// The API's answer for a box too large to list (/api/v1/properties).
const ZOOM_IN = "Zoom in to list sales";

type Card = { content: CardContent; x?: number; y?: number; pinned: boolean } | null;
export type ListState =
  | { status: "zoom" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ok"; data: PropertyList };

/** `v` is the data version: Martin caches tiles by URL, so a new monthly run gets new URLs. */
function tileUrl(source: "sales" | "price-hex", query: URLSearchParams, version: string): string {
  const q = new URLSearchParams(query);
  if (version) q.set("v", version);
  const qs = q.toString();
  return `${window.location.origin}${TILES}/${source}/{z}/{x}/{y}${qs ? `?${qs}` : ""}`;
}

function addDataLayers(map: MapLibreMap, filters: Filters, version: string) {
  const price = (p: string) => bandExpression(p) as ExpressionSpecification;
  map.addSource("sales", {
    type: "vector",
    tiles: [tileUrl("sales", filtersToParams(filters), version)],
    minzoom: 5,
    maxzoom: 16,
    promoteId: { sales: "id" },
    attribution: "Property Price Register © PSRA",
  });
  map.addSource("price-hex", {
    type: "vector",
    tiles: [tileUrl("price-hex", new URLSearchParams(), version)],
    minzoom: 5,
    maxzoom: 14,
  });
  map.addLayer({
    id: "hexes",
    type: "fill",
    source: "price-hex",
    "source-layer": "hexes",
    layout: { visibility: "none" },
    paint: {
      "fill-color": [
        "case",
        ["get", "suppressed"],
        SUPPRESSED_COLOR,
        price("median"),
      ] as ExpressionSpecification,
      "fill-opacity": ["case", ["get", "suppressed"], 0.3, 0.65],
      "fill-outline-color": "#ffffff",
    },
  });
  map.addLayer({
    id: "cells",
    type: "circle",
    source: "sales",
    "source-layer": "cells",
    maxzoom: POINT_ZOOM,
    paint: {
      "circle-color": price("median"),
      "circle-opacity": 0.85,
      // Sized by count, small enough that neighbouring cells stay apart at the national view.
      "circle-radius": [
        "interpolate",
        ["linear"],
        ["zoom"],
        5,
        ["interpolate", ["linear"], ["ln", ["get", "n"]], 0, 1.5, 8, 5],
        13,
        ["interpolate", ["linear"], ["ln", ["get", "n"]], 0, 3, 6, 12],
      ],
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 0.5,
    },
  });
  map.addLayer({
    id: "stacks",
    type: "circle",
    source: "sales",
    "source-layer": "stacks",
    minzoom: POINT_ZOOM,
    paint: {
      "circle-color": "#ffffff",
      "circle-radius": ["interpolate", ["linear"], ["ln", ["get", "n"]], 0, 8, 6, 18],
      "circle-stroke-color": price("median"),
      "circle-stroke-width": 3,
    },
  });
  map.addLayer({
    id: "stack-counts",
    type: "symbol",
    source: "sales",
    "source-layer": "stacks",
    minzoom: POINT_ZOOM,
    layout: {
      "text-field": ["to-string", ["get", "n"]],
      "text-font": ["Noto Sans Medium"],
      "text-size": 11,
      "text-allow-overlap": true,
    },
    paint: { "text-color": "#16181d" },
  });
  map.addLayer({
    id: "sales",
    type: "circle",
    source: "sales",
    "source-layer": "sales",
    minzoom: POINT_ZOOM,
    paint: {
      "circle-color": price("price"),
      "circle-radius": ["case", ["boolean", ["feature-state", "highlight"], false], 9, 6],
      "circle-stroke-color": [
        "case",
        ["boolean", ["feature-state", "highlight"], false],
        "#16181d",
        "#ffffff",
      ],
      "circle-stroke-width": 2,
    },
  });
}

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
  window.history.replaceState(null, "", `${window.location.pathname}?${p.toString()}`);
}

export function MapExplorer() {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [ready, setReady] = useState(false);
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [showHexes, setShowHexes] = useState(false);
  const [card, setCard] = useState<Card>(null);
  const [list, setList] = useState<ListState>({ status: "zoom" });
  const [mapError, setMapError] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const highlighted = useRef<string | null>(null);
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const pinned = useRef(false);
  const version = useRef("");
  const listRequest = useRef<AbortController | null>(null);
  // Map event handlers are registered once; they read the current filters from here.
  const state = useRef({ filters, showHexes });
  useEffect(() => {
    state.current = { filters, showHexes };
  }, [filters, showHexes]);

  const openProperty = useCallback((id: string, x?: number, y?: number, pin = false) => {
    pinned.current = pin || pinned.current;
    setCard({ content: { kind: "property", id, summary: null }, x, y, pinned: pinned.current });
    api
      .summary(id)
      .then((summary) =>
        setCard((c) =>
          c?.content.kind === "property" && c.content.id === id
            ? { ...c, content: { kind: "property", id, summary } }
            : c,
        ),
      )
      .catch((e: unknown) =>
        setCard((c) =>
          c?.content.kind === "property" && c.content.id === id
            ? {
                ...c,
                content: {
                  kind: "property",
                  id,
                  summary: null,
                  error:
                    e instanceof ApiError && e.status === 404
                      ? "No details for this sale."
                      : "Details could not be loaded.",
                },
              }
            : c,
        ),
      );
  }, []);

  const closeCard = useCallback(() => {
    pinned.current = false;
    setCard(null);
  }, []);

  const highlight = useCallback((id: string | null) => {
    const map = mapRef.current;
    if (!map || !map.getSource("sales")) return;
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
        addDataLayers(map, initial, version.current);
        if (hexesInitially) {
          map.setLayoutProperty("hexes", "visibility", "visible");
          for (const id of ["cells", "stacks", "stack-counts", "sales"])
            map.setLayoutProperty(id, "visibility", "none");
        }
        setReady(true);
        refreshList();
      });
      map.on("moveend", () => {
        if (!map) return;
        writeUrl(map, state.current.filters, state.current.showHexes);
        refreshList();
      });

      const hover = (e: MapLayerMouseEvent, show: () => void) => {
        if (!map) return;
        map.getCanvas().style.cursor = "pointer";
        if (pinned.current) return;
        clearTimeout(hoverTimer.current);
        hoverTimer.current = setTimeout(show, HOVER_DELAY_MS);
      };
      const leave = () => {
        if (!map) return;
        map.getCanvas().style.cursor = "";
        clearTimeout(hoverTimer.current);
        if (!pinned.current) setCard(null);
      };
      const propertyAt = (e: MapLayerMouseEvent) => String(e.features?.[0]?.properties?.id ?? "");
      map.on("mousemove", "sales", (e) => {
        const id = propertyAt(e);
        hover(e, () => openProperty(id, e.point.x, e.point.y));
      });
      map.on("click", "sales", (e) => {
        clearTimeout(hoverTimer.current);
        pinned.current = true;
        openProperty(propertyAt(e), e.point.x, e.point.y, true);
      });
      const groupCard = (e: MapLayerMouseEvent, kind: "stack" | "cell"): CardContent => {
        const p = e.features?.[0]?.properties ?? {};
        return kind === "stack"
          ? { kind, n: Number(p.n), median: Number(p.median), confidence: String(p.confidence) }
          : { kind, n: Number(p.n), median: Number(p.median) };
      };
      for (const [layer, kind] of [
        ["stacks", "stack"],
        ["cells", "cell"],
      ] as const) {
        map.on("mousemove", layer, (e) =>
          hover(e, () =>
            setCard({ content: groupCard(e, kind), x: e.point.x, y: e.point.y, pinned: false }),
          ),
        );
        map.on("click", layer, (e) => {
          clearTimeout(hoverTimer.current);
          pinned.current = true;
          setCard({ content: groupCard(e, kind), x: e.point.x, y: e.point.y, pinned: true });
        });
        map.on("mouseleave", layer, leave);
      }
      map.on("mouseleave", "sales", leave);
    })().catch(() => setMapError("The map could not be started in this browser."));
    return () => {
      cancelled = true;
      clearTimeout(hoverTimer.current);
      listRequest.current?.abort();
      map?.remove();
      mapRef.current = null;
      import("maplibre-gl").then((m) => m.removeProtocol("pmtiles")).catch(() => {});
    };
  }, [openProperty, refreshList]);

  // Filters and layer choice: new tile URLs, the list, and the address bar.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource("sales") as VectorTileSource).setTiles([
      tileUrl("sales", filtersToParams(filters), version.current),
    ]);
    map.setLayoutProperty("hexes", "visibility", showHexes ? "visible" : "none");
    for (const id of ["cells", "stacks", "stack-counts", "sales"]) {
      map.setLayoutProperty(id, "visibility", showHexes ? "none" : "visible");
    }
    writeUrl(map, filters, showHexes);
    refreshList();
  }, [filters, showHexes, ready, refreshList]);

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

  // Next to the pointer, flipped to its other side near the map's right and bottom edges.
  const CARD_W = 300;
  const CARD_H = 340;
  const cardPosition =
    card?.x !== undefined && card.y !== undefined
      ? {
          left: card.x + 12 + CARD_W > size.w ? Math.max(card.x - 12 - CARD_W, 8) : card.x + 12,
          top: Math.max(Math.min(card.y - 20, size.h - CARD_H), 8),
        }
      : undefined;

  return (
    <div className="flex h-[calc(100vh-7.5rem)] min-h-[32rem] flex-col md:flex-row">
      <aside className="order-2 max-h-[45vh] w-full shrink-0 overflow-y-auto border-t border-line bg-surface p-4 md:order-1 md:max-h-none md:w-80 md:border-r md:border-t-0">
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
            onFocusItem={(id) => highlight(id)}
            onOpenItem={(id) => {
              const item =
                list.status === "ok" ? list.data.items.find((i) => i.id === id) : undefined;
              highlight(id);
              if (item) mapRef.current?.easeTo({ center: [item.lng, item.lat] });
              openProperty(id, undefined, undefined, true);
            }}
          />
        </div>
      </aside>
      <div className="relative order-1 min-h-[20rem] flex-1 md:order-2">
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
          className="absolute left-3 top-3 rounded border border-line bg-surface px-3 py-1.5 text-sm font-medium text-ink shadow"
        >
          {locating ? "Finding you…" : "Near me"}
        </button>
        {mapError ? (
          <p
            role="alert"
            className="absolute left-3 top-14 max-w-xs rounded bg-surface px-3 py-2 text-sm text-ink shadow"
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
            <HoverCard content={card.content} onClose={card.pinned ? closeCard : undefined} />
          </div>
        ) : null}
      </div>
    </div>
  );
}
