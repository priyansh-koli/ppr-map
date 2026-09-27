import { layers, namedFlavor } from "@protomaps/basemaps";
import type { StyleSpecification } from "maplibre-gl";

/** Ireland and Northern Ireland; the map cannot pan off the basemap or away from the data. */
export const IRELAND_BOUNDS: [[number, number], [number, number]] = [
  [-10.8, 51.2],
  [-5.3, 55.5],
]; // the basemap extract's box (BASEMAP_BBOX in the Makefile)
export const IRELAND_CENTER: [number, number] = [-7.95, 53.4];

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
    layers: layers("protomaps", namedFlavor("light"), { lang: "en" }),
  };
}
