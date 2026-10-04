import type {
  ExpressionSpecification,
  GeoJSONSource,
  Map as MapLibreMap,
  MapGeoJSONFeature,
} from "maplibre-gl";

import { bandExpression, PRICE_BANDS, SUPPRESSED_COLOR } from "@/lib/price-bands";

// Points are drawn from z14 (migrations 0004 and 0006); below that, cells of 32 px.
export const POINT_ZOOM = 14;
export const SALE_LAYERS = ["cells", "stacks", "stack-counts", "sales"] as const;
export const INTERACTIVE_LAYERS = ["sales", "stacks", "cells"];

const INK = "#16181d";
const price = (p: string) => bandExpression(p) as ExpressionSpecification;

/** Radius by count, on a log scale shared by every zoom so a size means the same thing. */
const GROUP_RADIUS: ExpressionSpecification = [
  "interpolate",
  ["linear"],
  ["ln", ["get", "n"]],
  0,
  4,
  2.3,
  7,
  6.9,
  12,
  11.5,
  17,
];

/** 1234 → "1.2k", 12345 → "12k". */
const COMPACT_COUNT: ExpressionSpecification = [
  "case",
  [">=", ["get", "n"], 10000],
  ["concat", ["to-string", ["round", ["/", ["get", "n"], 1000]]], "k"],
  [">=", ["get", "n"], 1000],
  ["concat", ["to-string", ["/", ["round", ["/", ["get", "n"], 100]], 10]], "k"],
  ["to-string", ["get", "n"]],
];

/** Ink on the lightest band, white on the three darker ones: each pair clears 4.5:1. */
const COUNT_ON_BAND: ExpressionSpecification = [
  "step",
  ["get", "median"],
  INK,
  PRICE_BANDS[0].max,
  "#ffffff",
];

/**
 * The first basemap label layer. Sales are drawn beneath it, so place and street names stay
 * readable over them.
 */
export function firstLabelLayer(map: MapLibreMap): string | undefined {
  return map.getStyle().layers.find((l) => l.type === "symbol")?.id;
}

/** `v` is the tiles version (/meta): Martin caches tiles by URL, so a monthly run, or an admin
 * hiding or moving a property, gets new URLs. */
export function tileUrl(
  source: "sales" | "price-hex",
  query: URLSearchParams,
  version: string,
): string {
  const q = new URLSearchParams(query);
  if (version) q.set("v", version);
  const qs = q.toString();
  return `${window.location.origin}/api/v1/tiles/${source}/{z}/{x}/{y}${qs ? `?${qs}` : ""}`;
}

export function addDataLayers(map: MapLibreMap, salesQuery: URLSearchParams, version: string) {
  const beneathLabels = firstLabelLayer(map);
  map.addSource("sales", {
    type: "vector",
    tiles: [tileUrl("sales", salesQuery, version)],
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
  map.addSource("selected", { type: "geojson", data: emptySelection() });

  map.addLayer(
    {
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
    },
    beneathLabels,
  );
  // Zoomed out: one bubble per 32 px cell, at the mean position of its sales.
  map.addLayer(
    {
      id: "cells",
      type: "circle",
      source: "sales",
      "source-layer": "cells",
      maxzoom: POINT_ZOOM,
      paint: {
        "circle-color": price("median"),
        "circle-opacity": 0.9,
        "circle-radius": GROUP_RADIUS,
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 6, 1, 12, 1.5],
      },
    },
    beneathLabels,
  );
  map.addLayer(
    {
      id: "cell-counts",
      type: "symbol",
      source: "sales",
      "source-layer": "cells",
      maxzoom: POINT_ZOOM,
      // Only bubbles big enough to hold their count.
      filter: [">=", ["get", "n"], 10],
      layout: {
        "text-field": COMPACT_COUNT,
        "text-font": ["Noto Sans Medium"],
        "text-size": ["interpolate", ["linear"], ["ln", ["get", "n"]], 2.3, 9, 9, 11.5],
        // Place and street names are placed first and win: a count that would collide with
        // one is left out (the card still gives it). Counts never hide each other or a name.
        "text-allow-overlap": false,
        "text-ignore-placement": true,
      },
      paint: { "text-color": COUNT_ON_BAND },
    },
    beneathLabels,
  );
  map.addLayer(
    {
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
    },
    beneathLabels,
  );
  map.addLayer(
    {
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
        "text-ignore-placement": true,
      },
      paint: { "text-color": INK },
    },
    beneathLabels,
  );
  const hovered = ["boolean", ["feature-state", "highlight"], false] as ExpressionSpecification;
  map.addLayer(
    {
      id: "sales",
      type: "circle",
      source: "sales",
      "source-layer": "sales",
      minzoom: POINT_ZOOM,
      paint: {
        "circle-color": price("price"),
        "circle-radius": [
          "interpolate",
          ["linear"],
          ["zoom"],
          14,
          ["case", hovered, 7, 4.5],
          17,
          ["case", hovered, 10, 7],
        ],
        "circle-stroke-color": ["case", hovered, INK, "#ffffff"],
        "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 14, 1.25, 17, 2],
      },
    },
    beneathLabels,
  );

  // The selected property, above everything (labels too) and at every zoom: a soft halo and
  // an ink ring round a dot in its price colour.
  map.addLayer({
    id: "selected-halo",
    type: "circle",
    source: "selected",
    paint: { "circle-color": INK, "circle-opacity": 0.16, "circle-radius": 16 },
  });
  map.addLayer({
    id: "selected",
    type: "circle",
    source: "selected",
    paint: {
      "circle-color": ["case", ["has", "price"], price("price"), "#ffffff"],
      "circle-radius": 7,
      "circle-stroke-color": INK,
      "circle-stroke-width": 3,
    },
  });
}

export function setLayerVisibility(map: MapLibreMap, showHexes: boolean) {
  map.setLayoutProperty("hexes", "visibility", showHexes ? "visible" : "none");
  for (const id of [...SALE_LAYERS, "cell-counts"]) {
    map.setLayoutProperty(id, "visibility", showHexes ? "none" : "visible");
  }
}

export interface Selection {
  id: string;
  lngLat: [number, number];
  price?: number;
}

type SelectionData = Parameters<GeoJSONSource["setData"]>[0];

function emptySelection(): SelectionData {
  return { type: "FeatureCollection", features: [] };
}

export function showSelection(map: MapLibreMap, selection: Selection | null) {
  const source = map.getSource<GeoJSONSource>("selected");
  if (!source) return;
  source.setData(
    selection
      ? {
          type: "FeatureCollection",
          features: [
            {
              type: "Feature",
              geometry: { type: "Point", coordinates: selection.lngLat },
              properties: selection.price === undefined ? {} : { price: selection.price },
            },
          ],
        }
      : emptySelection(),
  );
}

/** One sale drawn on the map, as its tile describes it. */
export interface SalePoint {
  id: string;
  price: number;
  /** yyyymmdd, as in the tile. */
  date: number;
  lngLat: [number, number];
}

/**
 * The distinct sales among rendered features, newest first. Several properties placed on
 * the same street point overlap exactly, and each one must stay reachable.
 */
export function distinctSales(features: MapGeoJSONFeature[]): SalePoint[] {
  const seen = new Map<string, SalePoint>();
  for (const f of features) {
    if (f.layer.id !== "sales" || f.geometry.type !== "Point") continue;
    const id = String(f.properties.id ?? "");
    if (!id || seen.has(id)) continue;
    seen.set(id, {
      id,
      price: Number(f.properties.price),
      date: Number(f.properties.date),
      lngLat: f.geometry.coordinates as [number, number],
    });
  }
  return [...seen.values()].sort((a, b) => b.date - a.date);
}
