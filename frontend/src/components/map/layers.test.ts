import type { MapGeoJSONFeature } from "maplibre-gl";

import { distinctSales } from "./layers";

const feature = (layer: string, props: Record<string, unknown>, lngLat = [-6.27, 53.33]) =>
  ({
    layer: { id: layer },
    properties: props,
    geometry: { type: "Point", coordinates: lngLat },
  }) as unknown as MapGeoJSONFeature;

describe("distinctSales", () => {
  it("keeps each sale once, newest first, and ignores groups", () => {
    const sales = distinctSales([
      feature("sales", { id: "old", price: 300000, date: 20190105 }),
      feature("sales", { id: "new", price: 450000, date: 20260201 }),
      // The same feature again, from a neighbouring tile's buffer.
      feature("sales", { id: "old", price: 300000, date: 20190105 }),
      feature("stacks", { n: 12, median: 250000 }),
    ]);
    expect(sales.map((s) => s.id)).toEqual(["new", "old"]);
    expect(sales[0]).toEqual({
      id: "new",
      price: 450000,
      date: 20260201,
      lngLat: [-6.27, 53.33],
    });
  });
});
