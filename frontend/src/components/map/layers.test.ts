import type { MapGeoJSONFeature } from "maplibre-gl";

import { Color, createExpression } from "@maplibre/maplibre-gl-style-spec";

import { PRICE_BANDS, SUPPRESSED_COLOR } from "@/lib/price-bands";

import { distinctSales, GROUP_PRICE } from "./layers";

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

describe("GROUP_PRICE", () => {
  it("colours a group by its median, and greys one of fewer than 5 sales (no median)", () => {
    const parsed = createExpression(GROUP_PRICE, {
      type: "color",
      "property-type": "data-driven",
      expression: { interpolated: false, parameters: ["zoom", "feature"] },
    } as never);
    if (parsed.result !== "success") throw new Error(JSON.stringify(parsed.value));
    const colour = (properties: Record<string, unknown>) =>
      String(parsed.value.evaluate({ zoom: 10 }, { type: "Point", properties } as never));
    const same = (c: string) => String(Color.parse(c));
    expect(same(colour({ n: 12, median: 150000 }))).toBe(same(PRICE_BANDS[0].color));
    expect(same(colour({ n: 3 }))).toBe(same(SUPPRESSED_COLOR));
  });
});
