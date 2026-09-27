import { bandExpression, bandFor, PRICE_BANDS } from "./price-bands";

describe("price bands", () => {
  it("puts each price in exactly one band", () => {
    expect(bandFor(199_999).label).toBe("Under €200k");
    expect(bandFor(200_000).label).toBe("€200k–€350k");
    expect(bandFor(550_000).label).toBe("€550k and over");
    expect(bandFor(12_000_000).label).toBe("€550k and over");
  });

  it("builds the same steps as a MapLibre expression", () => {
    expect(bandExpression("price")).toEqual([
      "step",
      ["get", "price"],
      PRICE_BANDS[0].color,
      200_000,
      PRICE_BANDS[1].color,
      350_000,
      PRICE_BANDS[2].color,
      550_000,
      PRICE_BANDS[3].color,
    ]);
  });
});
