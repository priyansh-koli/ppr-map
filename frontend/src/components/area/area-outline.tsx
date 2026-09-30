/**
 * The area's shape as a small outline, drawn from its simplified GeoJSON: enough to see where
 * and what it is, without loading the map. Longitude is scaled by cos(latitude).
 */
type Ring = number[][];

function polygons(geometry: Record<string, unknown>): Ring[][] {
  const coords = geometry.coordinates as unknown;
  if (geometry.type === "Polygon") return [coords as Ring[]];
  if (geometry.type === "MultiPolygon") return coords as Ring[][];
  return [];
}

export function outlinePath(geometry: Record<string, unknown>, bbox: number[], size: number) {
  const [w = 0, s = 0, e = 1, n = 1] = bbox;
  const k = Math.cos((((s + n) / 2) * Math.PI) / 180);
  const width = Math.max((e - w) * k, 1e-9);
  const height = Math.max(n - s, 1e-9);
  const scale = (size - 8) / Math.max(width, height);
  const ox = (size - width * scale) / 2;
  const oy = (size - height * scale) / 2;
  const pt = ([lng = 0, lat = 0]: number[]) =>
    `${(ox + (lng - w) * k * scale).toFixed(1)},${(oy + (n - lat) * scale).toFixed(1)}`;
  return polygons(geometry)
    .flatMap((poly) => poly.map((ring) => `M${ring.map(pt).join("L")}Z`))
    .join("");
}

export function AreaOutline({
  geometry,
  bbox,
  label,
}: {
  geometry: Record<string, unknown>;
  bbox: number[];
  label: string;
}) {
  const size = 160;
  const d = outlinePath(geometry, bbox, size);
  if (!d) return null;
  return (
    <svg
      viewBox={`0 0 ${size} ${size}`}
      className="h-32 w-32 sm:h-40 sm:w-40"
      role="img"
      aria-label={`Outline of ${label}`}
    >
      <path
        d={d}
        fill="var(--color-accent-wash)"
        stroke="var(--color-accent)"
        strokeWidth={1.5}
        strokeLinejoin="round"
        fillRule="evenodd"
      />
    </svg>
  );
}
