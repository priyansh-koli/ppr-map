import type { Suggestion } from "./api/client";
import { describeSearch, shortEur, slugLabel } from "./describe";
import { DEFAULT_FILTERS, filtersToParams } from "./filters";
import { mapHref, placesOnly, withSuggestion } from "./search";

const suggestion = (s: Partial<Suggestion>): Suggestion => ({
  kind: "settlement",
  label: "Carlow",
  ...s,
});

describe("choosing a suggestion", () => {
  it("adds a place filter once, or none for an address", () => {
    const town = withSuggestion(DEFAULT_FILTERS, suggestion({ slug: "carlow-1f4955" }));
    expect(town?.area).toEqual(["carlow-1f4955"]);
    expect(withSuggestion(town!, suggestion({ slug: "carlow-1f4955" }))?.area).toEqual([
      "carlow-1f4955",
    ]);
    expect(
      withSuggestion(DEFAULT_FILTERS, suggestion({ kind: "county", slug: "cork" }))?.county,
    ).toEqual(["cork"]);
    expect(
      withSuggestion(DEFAULT_FILTERS, suggestion({ kind: "routing_key", routingKey: "D08" }))
        ?.routingKey,
    ).toEqual(["D08"]);
    expect(
      withSuggestion(DEFAULT_FILTERS, suggestion({ kind: "property", propertyId: "p1" })),
    ).toBeNull();
  });

  it("resets filters but keeps the places", () => {
    const f = {
      ...DEFAULT_FILTERS,
      county: ["cork"],
      priceMax: 300000,
      near: "53.1,-6.2",
      radiusM: 500,
    };
    expect(filtersToParams(placesOnly(f)).toString()).toBe(
      "county=cork&near=53.1%2C-6.2&radiusM=500",
    );
  });

  it("opens the map on the results' box", () => {
    const href = mapHref(new URLSearchParams("county=carlow&sort=price"), [-7.0, 52.5, -6.5, 52.9]);
    const p = new URLSearchParams(href.split("?")[1]);
    expect(href.startsWith("/map?")).toBe(true);
    expect(p.get("county")).toBe("carlow");
    expect(p.has("sort")).toBe(false);
    expect(Number(p.get("lat"))).toBeCloseTo(52.7);
    expect(Number(p.get("z"))).toBeGreaterThan(8);
  });
});

describe("a search in words", () => {
  it("names places, prices and the sort", () => {
    expect(
      describeSearch(
        {
          area: "carlow-1f4955",
          county: "kerry",
          priceMin: "200000",
          priceMax: "1250000",
          type: "new",
          sort: "-change",
        },
        { "carlow-1f4955": "Carlow town" },
      ),
    ).toBe("Carlow town · Kerry · €200k–€1.3m · new builds · biggest rise first");
    expect(describeSearch({})).toBe("All sales in Ireland");
  });

  it("never shows where 'my location' was", () => {
    expect(describeSearch({ near: "my-location", radiusM: "2000" })).toBe(
      "within 2.0 km of my location",
    );
  });

  it("makes slugs readable without the lookup", () => {
    expect(slugLabel("ed-carlow-rural-1a2b3c")).toBe("Carlow Rural");
    expect(slugLabel("sa-268113017-02")).toBe("Small Area 268113017-02");
    expect(shortEur(450000)).toBe("€450k");
  });
});
