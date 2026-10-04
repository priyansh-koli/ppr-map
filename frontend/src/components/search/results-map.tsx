"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import type { GeoJSONSource, Map as MapLibreMap, VectorTileSource } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

import { basemapStyle, IRELAND_BOUNDS, IRELAND_CENTER } from "@/components/map/basemap";
import {
  addDataLayers,
  distinctSales,
  INTERACTIVE_LAYERS,
  POINT_ZOOM,
  tileUrl,
} from "@/components/map/layers";
import { toBox } from "@/lib/filters";

type Circle = { near: string; radiusM: number } | null;

/** A polygon approximating a circle on the ground, for the "within X of" outline. */
export function circlePolygon(lat: number, lng: number, radiusM: number, steps = 64) {
  const dLat = radiusM / 111_320;
  const dLng = radiusM / (111_320 * Math.cos((lat * Math.PI) / 180));
  const ring = Array.from({ length: steps + 1 }, (_, i) => {
    const a = (i / steps) * 2 * Math.PI;
    return [lng + dLng * Math.cos(a), lat + dLat * Math.sin(a)];
  });
  return {
    type: "Feature" as const,
    geometry: { type: "Polygon" as const, coordinates: [ring] },
    properties: {},
  };
}

function circleData(circle: Circle) {
  if (!circle) return { type: "FeatureCollection" as const, features: [] };
  const [lat = 0, lng = 0] = circle.near.split(",").map(Number);
  return {
    type: "FeatureCollection" as const,
    features: [circlePolygon(lat, lng, circle.radiusM)],
  };
}

/**
 * The search's matches on the map: the same tiles as the map explorer with the same filters,
 * so the map and the list cannot disagree. It fits itself to the results; hovering a result
 * in the list marks it here once the map is close enough to draw single sales.
 */
export function ResultsMap({
  query,
  bbox,
  circle,
  version,
  highlightId,
  onOpen,
}: {
  query: URLSearchParams;
  bbox: number[] | null;
  circle: Circle;
  version: string;
  highlightId: string | null;
  onOpen: (id: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const highlighted = useRef<string | null>(null);
  const openRef = useRef(onOpen);
  useEffect(() => {
    openRef.current = onOpen;
  }, [onOpen]);
  const initial = useRef({ query, circle, version });

  useEffect(() => {
    if (!container.current) return;
    let map: MapLibreMap | undefined;
    let cancelled = false;
    (async () => {
      const maplibregl = await import("maplibre-gl");
      const { Protocol } = await import("pmtiles");
      if (cancelled || !container.current) return;
      maplibregl.setWorkerUrl(`/maplibre/${maplibregl.getVersion()}/maplibre-gl-worker.mjs`);
      const protocol = new Protocol();
      maplibregl.addProtocol("pmtiles", protocol.tile);
      map = new maplibregl.Map({
        container: container.current,
        style: basemapStyle(window.location.origin, { terrain: false }),
        center: IRELAND_CENTER,
        zoom: 6,
        maxBounds: IRELAND_BOUNDS,
        attributionControl: { compact: true },
        cooperativeGestures: true,
      });
      mapRef.current = map;
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      map.on("error", (e) => console.error(e.error));
      map.on("load", () => {
        if (!map) return;
        addDataLayers(map, initial.current.query, initial.current.version);
        map.addSource("radius", { type: "geojson", data: circleData(initial.current.circle) });
        map.addLayer({
          id: "radius",
          type: "line",
          source: "radius",
          paint: { "line-color": "#16181d", "line-width": 1.5, "line-dasharray": [2, 2] },
        });
        setReady(true);
      });
      map.on("mousemove", (e) => {
        if (!map) return;
        const hits = map.queryRenderedFeatures(e.point, { layers: INTERACTIVE_LAYERS });
        map.getCanvas().style.cursor = hits.length ? "pointer" : "";
      });
      map.on("click", (e) => {
        if (!map) return;
        const { x, y } = e.point;
        const hits = map.queryRenderedFeatures(
          [
            [x - 5, y - 5],
            [x + 5, y + 5],
          ],
          { layers: INTERACTIVE_LAYERS },
        );
        const [sale] = distinctSales(hits);
        const group = hits.find((f) => f.layer.id !== "sales");
        if (sale) openRef.current(sale.id);
        else if (group?.geometry.type === "Point")
          map.easeTo({
            center: group.geometry.coordinates as [number, number],
            zoom: Math.min(map.getZoom() + 3, POINT_ZOOM + 0.5),
          });
      });
    })().catch(() => setFailed(true));
    return () => {
      cancelled = true;
      map?.remove();
      mapRef.current = null;
      import("maplibre-gl").then((m) => m.removeProtocol("pmtiles")).catch(() => {});
    };
  }, []);

  // Keyed by value: the page passes a new circle object on every render (hovering a result
  // re-renders it), and new tile URLs make MapLibre reload every tile (P1 #28).
  const queryKey = query.toString();
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource("sales") as VectorTileSource).setTiles([
      tileUrl("sales", new URLSearchParams(queryKey), version),
    ]);
  }, [queryKey, version, ready]);

  const circleKey = circle ? `${circle.near}|${circle.radiusM}` : "";
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const [near = "", radius = ""] = circleKey.split("|");
    const shown = circleKey ? { near, radiusM: Number(radius) } : null;
    map.getSource<GeoJSONSource>("radius")?.setData(circleData(shown));
  }, [circleKey, ready]);

  const bboxKey = bbox?.join(",") ?? "";
  useEffect(() => {
    const map = mapRef.current;
    const box = toBox(bboxKey || null);
    if (!map || !ready || !box) return;
    const [w, s, e, n] = box;
    map.fitBounds(
      [
        [w, s],
        [e, n],
      ],
      { padding: 32, maxZoom: 15, duration: 600 },
    );
  }, [bboxKey, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !map.getSource("sales")) return;
    const set = (id: string, on: boolean) =>
      map.setFeatureState({ source: "sales", sourceLayer: "sales", id }, { highlight: on });
    if (highlighted.current) set(highlighted.current, false);
    highlighted.current = highlightId;
    if (highlightId) set(highlightId, true);
  }, [highlightId, ready]);

  return (
    <div className="relative h-full w-full">
      <div
        ref={container}
        className="h-full w-full"
        role="region"
        aria-label="Map of the matching sales"
      />
      {failed ? (
        <p className="absolute inset-x-3 top-3 window px-3 py-2 text-sm">
          The map could not be started in this browser; the list has every result.
        </p>
      ) : null}
    </div>
  );
}
