import { layers, namedFlavor } from "@protomaps/basemaps";
import type { LayerSpecification, StyleSpecification, TerrainSpecification } from "maplibre-gl";

/** Ireland and Northern Ireland; the map cannot pan off the basemap or away from the data. */
export const IRELAND_BOUNDS: [[number, number], [number, number]] = [
  [-10.8, 51.2],
  [-5.3, 55.5],
]; // the basemap extract's box (BASEMAP_BBOX in the Makefile)
export const IRELAND_CENTER: [number, number] = [-7.95, 53.4];

/** Relief in the 3D view: Ireland's hills are low, so they are raised a little. */
export const TERRAIN: TerrainSpecification = { source: "terrain", exaggeration: 1.5 };

const CASING = "#c9c2b5";
const BUILDING = "#d8d1c5";
const BUILDING_EDGE = "#b5ac9e";

/**
 * The light flavour with road edges that show. Its casings (#e0e0e0) all but vanish on the
 * land colour (#e2dfda), which the price ramp was validated against (D-038) and so stays.
 */
const FLAVOR = {
  ...namedFlavor("light"),
  minor_service_casing: CASING,
  minor_casing: CASING,
  link_casing: CASING,
  major_casing_early: CASING,
  major_casing_late: CASING,
  highway_casing_early: CASING,
  highway_casing_late: CASING,
  bridges_minor_casing: CASING,
  bridges_link_casing: CASING,
  bridges_major_casing: CASING,
  bridges_highway_casing: CASING,
  buildings: BUILDING,
};

/**
 * Place and street names are drawn above the sales, so they need a firmer halo than the
 * basemap's own 1 px of grey to stay readable over the price colours. Towns and
 * neighbourhoods also get darker text: the flavour's grey is below 3:1 on the land colour.
 * Building footprints get an edge, so a terrace reads as separate houses.
 */
const PAINT: Record<string, Record<string, unknown>> = {
  places_locality: { "text-color": "#3c4048", "text-halo-color": "#ffffff", "text-halo-width": 2 },
  places_subplace: { "text-color": "#5c5c5c", "text-halo-color": "#ffffff", "text-halo-width": 2 },
  places_region: { "text-halo-color": "#ffffff", "text-halo-width": 1.5 },
  roads_labels_major: { "text-halo-width": 1.75 },
  roads_labels_minor: { "text-halo-width": 1.75 },
  buildings: {
    "fill-color": BUILDING,
    "fill-outline-color": BUILDING_EDGE,
    "fill-opacity": ["interpolate", ["linear"], ["zoom"], 13, 0.4, 15, 1],
  },
};

function withPaint(layer: LayerSpecification): LayerSpecification {
  const paint = PAINT[layer.id];
  return paint && "paint" in layer
    ? ({ ...layer, paint: { ...layer.paint, ...paint } } as LayerSpecification)
    : layer;
}

/** Shaded relief, beneath the roads, fading as the map zooms in to streets. */
const HILLSHADE: LayerSpecification = {
  id: "hillshade",
  type: "hillshade",
  source: "hillshade",
  paint: {
    "hillshade-exaggeration": ["interpolate", ["linear"], ["zoom"], 6, 0.45, 12, 0.35, 16, 0.12],
    "hillshade-shadow-color": "#5b4f3c",
    "hillshade-highlight-color": "#ffffff",
    "hillshade-accent-color": "#8a7d68",
  },
};

/**
 * Buildings raised to their height, only where OpenStreetMap records one (a minority, mostly
 * in city centres). The rest stay flat footprints: a guessed height could be read as a fact
 * about a property. They grow in from z14 to z15.
 */
const BUILDINGS_3D: LayerSpecification = {
  id: "buildings-3d",
  type: "fill-extrusion",
  source: "protomaps",
  "source-layer": "buildings",
  minzoom: 14,
  filter: [
    "all",
    ["in", ["get", "kind"], ["literal", ["building", "building_part"]]],
    ["has", "height"],
  ],
  paint: {
    "fill-extrusion-color": BUILDING,
    "fill-extrusion-height": ["interpolate", ["linear"], ["zoom"], 14, 0, 15, ["get", "height"]],
    "fill-extrusion-base": [
      "interpolate",
      ["linear"],
      ["zoom"],
      14,
      0,
      15,
      ["coalesce", ["get", "min_height"], 0],
    ],
    "fill-extrusion-opacity": 0.92,
    "fill-extrusion-vertical-gradient": true,
  },
};

// The Copernicus DEM licence names both producers; MapLibre shows a shared string once.
const TERRAIN_ATTRIBUTION =
  '<a href="https://mapterhorn.com/attribution">Mapterhorn</a> · Copernicus DEM © DLR e.V. 2010–2014, © Airbus Defence and Space GmbH 2014–2018 (EU, ESA)';

/** Where the hillshade goes: above land use and water, beneath every road. */
const BENEATH_ROADS = "roads_tunnels_other_casing";

/**
 * The self-hosted Protomaps basemap (D-005, `make basemap`): the PMTiles extracts, fonts and
 * sprites all come from our own origin, so viewing the map calls no third party. `terrain` is
 * false when the elevation extract has not been downloaded: the map is then flat, as before.
 */
export function basemapStyle(origin: string, { terrain = true } = {}): StyleSpecification {
  const base = layers("protomaps", FLAVOR, { lang: "en" }).map(withPaint);
  const out: LayerSpecification[] = [];
  for (const layer of base) {
    if (terrain && layer.id === BENEATH_ROADS) out.push(HILLSHADE);
    out.push(layer);
    if (layer.id === "buildings") out.push(BUILDINGS_3D);
  }
  const dem = {
    type: "raster-dem" as const,
    url: `pmtiles://${origin}/basemap/terrain.pmtiles`,
    encoding: "terrarium" as const,
    tileSize: 512,
    attribution: TERRAIN_ATTRIBUTION,
  };
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
      // Two sources on one file: MapLibre advises against sharing one between terrain and
      // hillshade.
      ...(terrain ? { terrain: dem, hillshade: dem } : {}),
    },
    // Seen only when the map is tilted: a pale sky fading into the page colour.
    sky: {
      "sky-color": "#cfe0ea",
      "horizon-color": "#eef0ec",
      "fog-color": "#f4f1ea",
      "sky-horizon-blend": 0.6,
      "horizon-fog-blend": 0.7,
      "fog-ground-blend": 0.92,
      "atmosphere-blend": 0,
    },
    // Softer light on raised buildings: the default makes their walls heavy on this palette.
    light: { anchor: "viewport", color: "#ffffff", intensity: 0.25, position: [1.2, 200, 35] },
    layers: out,
  };
}
