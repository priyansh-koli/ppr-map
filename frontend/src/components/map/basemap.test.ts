import { validateStyleMin } from "@maplibre/maplibre-gl-style-spec";

import { basemapStyle } from "./basemap";

const ids = (terrain: boolean) =>
  basemapStyle("http://localhost", { terrain }).layers.map((l) => l.id);

describe("basemapStyle", () => {
  it.each([true, false])("is a valid MapLibre style (terrain: %s)", (terrain) => {
    const errors = validateStyleMin(basemapStyle("http://localhost", { terrain }) as never);
    expect(errors.map((e: { message: string }) => e.message)).toEqual([]);
  });

  it("shades the relief beneath the roads, and only when the elevation extract exists", () => {
    const withTerrain = ids(true);
    expect(withTerrain.indexOf("hillshade")).toBeLessThan(withTerrain.indexOf("roads_minor"));
    expect(ids(false)).not.toContain("hillshade");
  });

  it("raises only the buildings that record a height, above their flat footprints", () => {
    const style = basemapStyle("http://localhost");
    const layers = style.layers.map((l) => l.id);
    expect(layers.indexOf("buildings-3d")).toBe(layers.indexOf("buildings") + 1);
    const extruded = style.layers.find((l) => l.id === "buildings-3d");
    expect(JSON.stringify(extruded && "filter" in extruded ? extruded.filter : null)).toContain(
      '["has","height"]',
    );
  });
});
