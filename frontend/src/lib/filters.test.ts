import { DEFAULT_FILTERS, filtersToParams, parseFilters } from "./filters";

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
        "priceMin=abc&priceMax=-5&dateFrom=yesterday&type=castle&minConfidence=psychic",
      ),
    );
    expect(f).toEqual(DEFAULT_FILTERS);
  });
});
