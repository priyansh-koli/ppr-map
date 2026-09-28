import { CARD_W, placeCard } from "./card-position";

const MAP = { w: 1000, h: 800 };

describe("placeCard", () => {
  it("sits to the right of its point", () => {
    expect(placeCard({ x: 200, y: 300 }, MAP)).toEqual({ left: 216, top: 276 });
  });

  it("flips to the left near the right edge and stays inside vertically", () => {
    const at = placeCard({ x: 900, y: 790 }, MAP);
    expect(at?.left).toBe(900 - 16 - CARD_W);
    expect(at?.top).toBe(800 - 340 - 8);
  });

  it("docks when the point has left the view, or the map is too narrow", () => {
    expect(placeCard({ x: -5, y: 300 }, MAP)).toBeNull();
    expect(placeCard({ x: 200, y: 900 }, MAP)).toBeNull();
    expect(placeCard({ x: 100, y: 100 }, { w: 390, h: 400 })).toBeNull();
    expect(placeCard(null, MAP)).toBeNull();
  });
});
