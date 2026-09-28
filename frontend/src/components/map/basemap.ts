import { layers, namedFlavor } from "@protomaps/basemaps";
import type { LayerSpecification, StyleSpecification } from "maplibre-gl";

/** Ireland and Northern Ireland; the map cannot pan off the basemap or away from the data. */
export const IRELAND_BOUNDS: [[number, number], [number, number]] = [
  [-10.8, 51.2],
  [-5.3, 55.5],
]; // the basemap extract's box (BASEMAP_BBOX in the Makefile)
export const IRELAND_CENTER: [number, number] = [-7.95, 53.4];

/**
 * Place and street names are drawn above the sales, so they need a firmer halo than the
 * basemap's own 1 px of grey to stay readable over the price colours. Towns and
 * neighbourhoods also get darker text: the flavour's grey is below 3:1 on the land colour.
 */
const LABEL_PAINT: Record<string, Record<string, unknown>> = {
  places_locality: { "text-color": "#3c4048", "text-halo-color": "#ffffff", "text-halo-width": 2 },
  places_subplace: { "text-color": "#5c5c5c", "text-halo-color": "#ffffff", "text-halo-width": 2 },
  places_region: { "text-halo-color": "#ffffff", "text-halo-width": 1.5 },
  roads_labels_major: { "text-halo-width": 1.75 },
  roads_labels_minor: { "text-halo-width": 1.75 },
};

function withLabelPaint(layer: LayerSpecification): LayerSpecification {
  const paint = LABEL_PAINT[layer.id];
  return paint && layer.type === "symbol"
    ? { ...layer, paint: { ...layer.paint, ...paint } }
    : layer;
}

/**
 * The self-hosted Protomaps basemap (D-005, `make basemap`): the PMTiles extract, fonts and
 * sprites all come from our own origin, so viewing the map calls no third party.
 */
export function basemapStyle(origin: string): StyleSpecification {
  return {
    version: 8,
    glyphs: `${origin}/basemap/assets/fonts/{fontstack}/{range}.pbf`,
    sprite: `${origin}/basemap/assets/sprites/v4/light`,
    sources: {
      protomaps: {
        type: "vector",
        url: `pmtiles://${origin}/basemap/ireland.pmtiles`,
        attribution:
          '<a href="https://protomaps.com">Protomaps</a> © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
      },
    },
    layers: layers("protomaps", namedFlavor("light"), { lang: "en" }).map(withLabelPaint),
  };
}
