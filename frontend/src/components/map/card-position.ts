export const CARD_W = 300;
export const CARD_H = 340;
const GAP = 16;
const EDGE = 8;

/**
 * Where the details card goes: beside its point on the map, flipped to the point's left near
 * the right edge and kept inside the map vertically. `null` docks it in the corner instead:
 * on maps too narrow to hold a card beside a point (phones), or when the point has left the
 * view, so the card never points at something that is not there.
 */
export function placeCard(
  point: { x: number; y: number } | null,
  map: { w: number; h: number },
): { left: number; top: number } | null {
  if (!point || map.w < CARD_W * 1.6) return null;
  if (point.x < 0 || point.y < 0 || point.x > map.w || point.y > map.h) return null;
  const left =
    point.x + GAP + CARD_W > map.w ? Math.max(point.x - GAP - CARD_W, EDGE) : point.x + GAP;
  const top = Math.max(Math.min(point.y - 24, map.h - CARD_H - EDGE), EDGE);
  return { left, top };
}
