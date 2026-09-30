import { DEFAULT_FILTERS, filtersToParams, parseFilters, parseSort } from "./filters";

describe("map filters", () => {
  it("defaults to market sales at locality precision or better", () => {
    expect(parseFilters(new URLSearchParams())).toEqual(DEFAULT_FILTERS);
    expect(filtersToParams(DEFAULT_FILTERS).toString()).toBe("");
  });

  it("round-trips changed values through the URL", () => {
    const f = {
      ...DEFAULT_FILTERS,
      priceMin: 200000,
      dateFrom: "2024-01-01",
      type: "new" as const,
      excludeBulk: false,
      minConfidence: "street" as const,
    };
    expect(parseFilters(filtersToParams(f))).toEqual(f);
  });

  it("ignores values it does not understand", () => {
    const f = parseFilters(
      new URLSearchParams(
        "priceMin=abc&priceMax=-5&dateFrom=yesterday&dateTo=2025-02-30&type=castle&minConfidence=psychic",
      ),
    );
    expect(f).toEqual(DEFAULT_FILTERS);
  });

  it("round-trips place, VAT and distance filters", () => {
    const f = {
      ...DEFAULT_FILTERS,
      vat: "exclusive" as const,
      county: ["cork", "kerry"],
      area: ["carlow-1f4955", "sa-268113017-02"],
      routingKey: ["D08", "D6W"],
      near: "53.34123,-6.26012",
      radiusM: 2000,
      maxStopM: 500,
      maxSchoolM: 1000,
    };
    const params = filtersToParams(f);
    expect(params.get("county")).toBe("cork,kerry");
    expect(parseFilters(params)).toEqual(f);
  });

  it("drops list items and points it does not understand", () => {
    const f = parseFilters(
      new URLSearchParams(
        "county=Cork,narnia,cork&routingKey=d08,B12&area=ok-1,a/b&near=48.8,2.3&radiusM=500&maxStopM=5",
      ),
    );
    expect(f.county).toEqual(["cork"]);
    expect(f.routingKey).toEqual(["D08"]);
    expect(f.area).toEqual(["ok-1"]);
    expect(f.near).toBeNull();
    expect(f.radiusM).toBeNull(); // a radius means nothing without a point
    expect(f.maxStopM).toBeNull();
  });

  it("reads the sort, defaulting to the newest first", () => {
    expect(parseSort(new URLSearchParams("sort=-change"))).toBe("-change");
    expect(parseSort(new URLSearchParams("sort=address"))).toBe("-date");
  });
});
