import type { PropertyDetail } from "@/lib/api/client";
import { formatEur, formatEurShort, formatMonth } from "@/lib/format";

type Series = NonNullable<PropertyDetail["areaSeries"]>;

const W = 640;
const H = 220;
const PAD = { top: 12, right: 12, bottom: 28, left: 64 };

/**
 * The area's rolling 12-month median, as one line. Suppressed months (fewer than 5 sales)
 * are gaps, not guesses; provisional months are dashed. The table below carries the same
 * numbers for screen readers and anyone who prefers them.
 */
export function AreaTrend({ series }: { series: Series }) {
  const pts = series.points.filter((p) => p.median !== null && p.median !== undefined);
  const first = series.points.at(0);
  const final = series.points.at(-1);
  const lastPoint = pts.at(-1);
  if (pts.length < 2 || !first || !final || !lastPoint) {
    return <p className="text-muted">Not enough sales in {series.area.name} for a trend.</p>;
  }
  const values = pts.map((p) => p.median as number);
  const lo = Math.min(...values) * 0.95;
  const hi = Math.max(...values) * 1.05;
  const t0 = Date.parse(first.periodStart);
  const t1 = Date.parse(final.periodStart);
  const x = (iso: string) =>
    PAD.left + ((Date.parse(iso) - t0) / Math.max(t1 - t0, 1)) * (W - PAD.left - PAD.right);
  const y = (v: number) => PAD.top + (1 - (v - lo) / (hi - lo)) * (H - PAD.top - PAD.bottom);

  // Consecutive runs of shown months, split where a month is suppressed or turns provisional.
  const runs: { provisional: boolean; points: [number, number][] }[] = [];
  for (const p of series.points) {
    if (p.median === null || p.median === undefined) {
      runs.push({ provisional: p.provisional, points: [] });
      continue;
    }
    const last = runs.at(-1);
    const point: [number, number] = [x(p.periodStart), y(p.median)];
    if (!last || last.provisional !== p.provisional) {
      const tail = last?.points.at(-1);
      const joined: [number, number][] = tail ? [tail, point] : [point];
      runs.push({ provisional: p.provisional, points: joined });
    } else {
      last.points.push(point);
    }
  }
  const ticks = [lo, (lo + hi) / 2, hi];
  return (
    <figure className="space-y-2">
      <figcaption className="text-sm text-muted">
        Median sale price over the previous 12 months, {series.area.name}. Dashed: provisional.
      </figcaption>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full max-w-2xl"
        role="img"
        aria-label={`Median price trend for ${series.area.name}`}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y(t)}
              y2={y(t)}
              stroke="var(--color-line)"
              strokeWidth={1}
            />
            <text
              x={PAD.left - 8}
              y={y(t) + 4}
              textAnchor="end"
              fontSize={11}
              fill="var(--color-muted)"
            >
              {formatEurShort(t)}
            </text>
          </g>
        ))}
        <text x={PAD.left} y={H - 8} fontSize={11} fill="var(--color-muted)">
          {formatMonth(first.periodStart)}
        </text>
        <text x={W - PAD.right} y={H - 8} textAnchor="end" fontSize={11} fill="var(--color-muted)">
          {formatMonth(final.periodStart)}
        </text>
        {runs
          .filter((r) => r.points.length > 1)
          .map((r, i) => (
            <polyline
              key={i}
              points={r.points.map((p) => p.join(",")).join(" ")}
              fill="none"
              stroke="#2a78d6"
              strokeWidth={2}
              strokeLinejoin="round"
              strokeDasharray={r.provisional ? "5 4" : undefined}
            />
          ))}
        {pts.map((p) => (
          <circle
            key={p.periodStart}
            cx={x(p.periodStart)}
            cy={y(p.median as number)}
            r={6}
            fill="transparent"
          >
            <title>{`${formatMonth(p.periodStart)}: ${formatEur(p.median as number)} (${p.n} sales${p.provisional ? ", provisional" : ""})`}</title>
          </circle>
        ))}
        <circle
          cx={x(lastPoint.periodStart)}
          cy={y(lastPoint.median as number)}
          r={4}
          fill="#2a78d6"
          stroke="var(--color-surface)"
          strokeWidth={2}
        />
      </svg>
      <details className="text-sm">
        <summary className="cursor-pointer text-accent">Show as a table</summary>
        <table className="mt-2 w-full max-w-md text-left">
          <thead>
            <tr className="text-muted">
              <th className="py-1 font-medium">12 months to</th>
              <th className="py-1 font-medium">Median</th>
              <th className="py-1 font-medium">Sales</th>
            </tr>
          </thead>
          <tbody>
            {series.points.map((p) => (
              <tr key={p.periodStart} className="border-t border-line">
                <td className="py-1">{formatMonth(p.periodStart)}</td>
                <td className="py-1">
                  {p.median !== null && p.median !== undefined
                    ? formatEur(p.median)
                    : "not shown (fewer than 5)"}
                  {p.provisional ? " (provisional)" : ""}
                </td>
                <td className="py-1">{p.n}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
