"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { type AreaStats, api, type Distribution, type SeriesPoint } from "@/lib/api/client";
import { formatEur, formatEurShort, formatMonth } from "@/lib/format";

// The area is the one series the page is about (data blue, D-038/D-043); Ireland is context
// in grey (the "highlight one, grey the rest" pattern). Validated with the dataviz checks on
// both surfaces: ΔE 16.3 protan / 18.2 normal, both 3:1 or more.
const AREA = "#2a78d6";
const IRELAND = "#8a877e";

type PeriodKind = AreaStats["periodKind"];
type Segment = AreaStats["segment"];

const PERIOD_LABEL: Record<PeriodKind, string> = {
  rolling_12m: "12-month rolling",
  month: "Month",
  quarter: "Quarter",
  year: "Year",
};
const SEGMENT_LABEL: Record<Segment, string> = {
  all: "All homes",
  new: "New",
  second_hand: "Second-hand",
};

export function periodLabel(kind: PeriodKind, iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  if (kind === "year") return String(d.getUTCFullYear());
  if (kind === "quarter") return `Q${Math.floor(d.getUTCMonth() / 3) + 1} ${d.getUTCFullYear()}`;
  if (kind === "rolling_12m") return `12 months to ${formatMonth(iso)}`;
  return formatMonth(iso);
}

const W = 720;
const H = 260;
const PAD = { top: 16, right: 78, bottom: 28, left: 64 };

type Run = { provisional: boolean; points: [number, number][] };

/** Consecutive shown periods; a suppressed period is a gap, a provisional one dashed. */
function runs(points: SeriesPoint[], x: (iso: string) => number, y: (v: number) => number): Run[] {
  const out: Run[] = [];
  for (const p of points) {
    if (p.median === null || p.median === undefined) {
      out.push({ provisional: p.provisional, points: [] });
      continue;
    }
    const last = out.at(-1);
    const point: [number, number] = [x(p.periodStart), y(p.median)];
    if (!last || last.provisional !== p.provisional) {
      const tail = last?.points.at(-1);
      out.push({ provisional: p.provisional, points: tail ? [tail, point] : [point] });
    } else last.points.push(point);
  }
  return out.filter((r) => r.points.length > 1);
}

function niceTicks(lo: number, hi: number): number[] {
  const step =
    [25_000, 50_000, 100_000, 200_000, 250_000, 500_000].find((s) => (hi - lo) / s <= 5) ??
    1_000_000;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) out.push(v);
  return out;
}

function Legend({ name }: { name: string }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
      <li className="flex items-center gap-1.5">
        <svg width="18" height="6" aria-hidden="true">
          <line x1="0" x2="18" y1="3" y2="3" stroke={AREA} strokeWidth="2" strokeLinecap="round" />
        </svg>
        {name}
      </li>
      <li className="flex items-center gap-1.5">
        <svg width="18" height="6" aria-hidden="true">
          <line
            x1="0"
            x2="18"
            y1="3"
            y2="3"
            stroke={IRELAND}
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
        Ireland
      </li>
      <li className="flex items-center gap-1.5">
        <svg width="18" height="6" aria-hidden="true">
          <line
            x1="0"
            x2="18"
            y1="3"
            y2="3"
            stroke="var(--color-muted)"
            strokeWidth="2"
            strokeDasharray="4 3"
          />
        </svg>
        Provisional (late filings still arrive)
      </li>
    </ul>
  );
}

/** Median price over time, the area against Ireland, with a crosshair readout. */
function MedianChart({ data }: { data: AreaStats }) {
  const [hover, setHover] = useState<number | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  const points = data.points;
  const national = useMemo(
    () => new Map(data.national.map((p) => [p.periodStart, p])),
    [data.national],
  );
  const values = [
    ...points.map((p) => p.median),
    ...points.map((p) => national.get(p.periodStart)?.median),
  ].filter((v): v is number => typeof v === "number");
  if (points.length < 2 || values.length < 2) {
    return (
      <p className="text-sm text-muted">
        Too few sales in {data.area.name} for a price trend: periods with fewer than 5 sales are not
        shown.
      </p>
    );
  }
  const lo = Math.max(0, Math.min(...values) * 0.92);
  const hi = Math.max(...values) * 1.05;
  const iw = W - PAD.left - PAD.right;
  const x = (iso: string) => {
    const i = points.findIndex((p) => p.periodStart === iso);
    return PAD.left + (points.length === 1 ? iw / 2 : (i / (points.length - 1)) * iw);
  };
  const y = (v: number) => PAD.top + (1 - (v - lo) / (hi - lo)) * (H - PAD.top - PAD.bottom);
  const nationalPoints = points.map(
    (p) => national.get(p.periodStart) ?? { ...p, median: null, n: 0, suppressed: true },
  );
  const lastArea = [...points].reverse().find((p) => p.median != null);
  const lastIreland = [...nationalPoints].reverse().find((p) => p.median != null);
  const labels = [
    lastArea && { text: data.area.name, y: y(lastArea.median as number) },
    lastIreland && { text: "Ireland", y: y(lastIreland.median as number) },
  ].filter(Boolean) as { text: string; y: number }[];
  // Converging ends: leave them to the legend rather than stacking labels (dataviz rule).
  const endLabels = labels.length === 2 && Math.abs(labels[0]!.y - labels[1]!.y) < 14 ? [] : labels;

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const box = svg.current?.getBoundingClientRect();
    if (!box) return;
    const px = ((e.clientX - box.left) / box.width) * W;
    const i = Math.round(((px - PAD.left) / iw) * (points.length - 1));
    setHover(Math.min(points.length - 1, Math.max(0, i)));
  };
  const hp = hover !== null ? points[hover] : undefined;
  const hn = hp ? national.get(hp.periodStart) : undefined;
  const first = points[0]!;
  const final = points.at(-1)!;
  return (
    <div className="relative">
      <svg
        ref={svg}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full touch-none"
        role="img"
        aria-label={`Median price, ${data.area.name} and Ireland; the table below has every value`}
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      >
        {niceTicks(lo, hi).map((t) => (
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
          {periodLabel(data.periodKind, first.periodStart).replace("12 months to ", "")}
        </text>
        <text x={W - PAD.right} y={H - 8} textAnchor="end" fontSize={11} fill="var(--color-muted)">
          {periodLabel(data.periodKind, final.periodStart).replace("12 months to ", "")}
        </text>
        {runs(nationalPoints, x, y).map((r, i) => (
          <polyline
            key={`n${i}`}
            points={r.points.map((p) => p.join(",")).join(" ")}
            fill="none"
            stroke={IRELAND}
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
            strokeDasharray={r.provisional ? "5 4" : undefined}
          />
        ))}
        {runs(points, x, y).map((r, i) => (
          <polyline
            key={`a${i}`}
            points={r.points.map((p) => p.join(",")).join(" ")}
            fill="none"
            stroke={AREA}
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
            strokeDasharray={r.provisional ? "5 4" : undefined}
          />
        ))}
        {lastArea ? (
          <circle
            cx={x(lastArea.periodStart)}
            cy={y(lastArea.median as number)}
            r={4}
            fill={AREA}
            stroke="var(--color-surface)"
            strokeWidth={2}
          />
        ) : null}
        {endLabels.map((l) => (
          <text
            key={l.text}
            x={W - PAD.right + 8}
            y={l.y + 4}
            fontSize={11}
            fill="var(--color-ink-2)"
          >
            {l.text.length > 11 ? `${l.text.slice(0, 10)}…` : l.text}
          </text>
        ))}
        {hp ? (
          <line
            x1={x(hp.periodStart)}
            x2={x(hp.periodStart)}
            y1={PAD.top}
            y2={H - PAD.bottom}
            stroke="var(--color-line-strong)"
            strokeWidth={1}
          />
        ) : null}
      </svg>
      {hp ? (
        <div
          className="window pointer-events-none absolute top-2 z-10 px-3 py-2 text-xs"
          style={{
            left: `${(x(hp.periodStart) / W) * 100}%`,
            transform:
              x(hp.periodStart) > W / 2 ? "translateX(calc(-100% - 8px))" : "translateX(8px)",
          }}
          role="status"
        >
          <p className="font-medium text-ink">
            {periodLabel(data.periodKind, hp.periodStart)}
            {hp.provisional ? " · provisional" : ""}
          </p>
          <p className="mt-1 flex items-center gap-1.5">
            <span
              className="inline-block h-0.5 w-3"
              style={{ background: AREA }}
              aria-hidden="true"
            />
            <strong className="text-ink">
              {hp.median != null ? formatEur(hp.median) : "fewer than 5 sales"}
            </strong>
            <span className="text-muted">
              {data.area.name}, {hp.n} sales
            </span>
          </p>
          {hn ? (
            <p className="flex items-center gap-1.5">
              <span
                className="inline-block h-0.5 w-3"
                style={{ background: IRELAND }}
                aria-hidden="true"
              />
              <strong className="text-ink">{hn.median != null ? formatEur(hn.median) : "–"}</strong>
              <span className="text-muted">Ireland</span>
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/** Sales per period: one series, so no legend; the heading names it. */
function VolumeChart({ data }: { data: AreaStats }) {
  const [hover, setHover] = useState<number | null>(null);
  const points = data.points;
  if (!points.length) return null;
  const max = Math.max(...points.map((p) => p.n), 1);
  const h = 140;
  const pad = { top: 10, bottom: 22, left: 64, right: 12 };
  const slot = (W - pad.left - pad.right) / points.length;
  const bw = Math.min(24, Math.max(1, slot - 2));
  const y = (n: number) => pad.top + (1 - n / max) * (h - pad.top - pad.bottom);
  const hp = hover !== null ? points[hover] : undefined;
  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${W} ${h}`}
        className="w-full"
        role="img"
        aria-label={`Sales per period in ${data.area.name}; the table below has every value`}
        onPointerLeave={() => setHover(null)}
      >
        <line
          x1={pad.left}
          x2={W - pad.right}
          y1={h - pad.bottom}
          y2={h - pad.bottom}
          stroke="var(--color-line)"
        />
        <text
          x={pad.left - 8}
          y={y(max) + 4}
          textAnchor="end"
          fontSize={11}
          fill="var(--color-muted)"
        >
          {max.toLocaleString("en-IE")}
        </text>
        {points.map((p, i) => {
          const cx = pad.left + slot * i + slot / 2;
          const top = y(p.n);
          const height = h - pad.bottom - top;
          const r = Math.min(4, bw / 2, height);
          return (
            <g key={p.periodStart} onPointerEnter={() => setHover(i)}>
              <rect
                x={cx - slot / 2}
                y={pad.top}
                width={slot}
                height={h - pad.top - pad.bottom}
                fill="transparent"
              />
              {height > 0 ? (
                <path
                  d={`M${cx - bw / 2},${h - pad.bottom} V${top + r} Q${cx - bw / 2},${top} ${cx - bw / 2 + r},${top} H${cx + bw / 2 - r} Q${cx + bw / 2},${top} ${cx + bw / 2},${top + r} V${h - pad.bottom} Z`}
                  fill={AREA}
                  opacity={p.provisional ? 0.45 : hover === i ? 0.8 : 1}
                />
              ) : null}
            </g>
          );
        })}
      </svg>
      {hp ? (
        <p
          className="window pointer-events-none absolute right-2 top-0 px-3 py-1.5 text-xs"
          role="status"
        >
          <strong className="text-ink">{hp.n.toLocaleString("en-IE")} sales</strong>{" "}
          <span className="text-muted">
            {periodLabel(data.periodKind, hp.periodStart)}
            {hp.provisional ? ", provisional" : ""}
          </span>
        </p>
      ) : null}
    </div>
  );
}

function SeriesTable({ data }: { data: AreaStats }) {
  const national = new Map(data.national.map((p) => [p.periodStart, p]));
  return (
    <details className="text-sm">
      <summary className="cursor-pointer text-accent">Show as a table</summary>
      <div className="mt-2 max-h-80 overflow-y-auto">
        <table className="w-full text-left">
          <thead className="sticky top-0 bg-surface">
            <tr className="text-muted">
              <th scope="col" className="py-1 pr-3 font-medium">
                Period
              </th>
              <th scope="col" className="py-1 pr-3 text-right font-medium">
                Sales
              </th>
              <th scope="col" className="py-1 pr-3 text-right font-medium">
                Median
              </th>
              <th scope="col" className="py-1 pr-3 text-right font-medium">
                Middle half
              </th>
              <th scope="col" className="py-1 text-right font-medium">
                Ireland median
              </th>
            </tr>
          </thead>
          <tbody>
            {[...data.points].reverse().map((p) => {
              const n = national.get(p.periodStart);
              return (
                <tr key={p.periodStart} className="border-t border-line">
                  <td className="py-1 pr-3">
                    {periodLabel(data.periodKind, p.periodStart)}
                    {p.provisional ? " (provisional)" : ""}
                  </td>
                  <td className="py-1 pr-3 text-right tabular-nums">
                    {p.n.toLocaleString("en-IE")}
                  </td>
                  <td className="py-1 pr-3 text-right tabular-nums">
                    {p.median != null ? formatEur(p.median) : "fewer than 5"}
                  </td>
                  <td className="py-1 pr-3 text-right tabular-nums">
                    {p.p25 != null && p.p75 != null
                      ? `${formatEurShort(p.p25)}–${formatEurShort(p.p75)}`
                      : "–"}
                  </td>
                  <td className="py-1 text-right tabular-nums">
                    {n?.median != null ? formatEur(n.median) : "–"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </details>
  );
}

/** The stats section: choose the period and segment; median against Ireland, then volume. */
export function AreaTrends({
  slug,
  name,
  periodKinds,
}: {
  slug: string;
  name: string;
  periodKinds: PeriodKind[];
}) {
  const [periodKind, setPeriodKind] = useState<PeriodKind>(
    periodKinds.includes("rolling_12m") ? "rolling_12m" : "year",
  );
  const [segment, setSegment] = useState<Segment>("all");
  const key = `${periodKind}|${segment}`;
  const [answer, setAnswer] = useState<{ key: string; data?: AreaStats; error?: boolean }>({
    key: "",
  });
  useEffect(() => {
    const request = new AbortController();
    api
      .areaStats(slug, new URLSearchParams({ periodKind, segment }), { signal: request.signal })
      .then((data) => setAnswer({ key, data }))
      .catch(() => {
        if (!request.signal.aborted) setAnswer({ key, error: true });
      });
    return () => request.abort();
  }, [slug, periodKind, segment, key]);
  const data = answer.data;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-3 text-sm">
        <label>
          <span className="block text-muted">Periods</span>
          <select
            className="mt-0.5 px-2.5 py-1.5"
            value={periodKind}
            onChange={(e) => setPeriodKind(e.target.value as PeriodKind)}
          >
            {periodKinds.map((k) => (
              <option key={k} value={k}>
                {PERIOD_LABEL[k]}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="block text-muted">Homes</span>
          <select
            className="mt-0.5 px-2.5 py-1.5"
            value={segment}
            onChange={(e) => setSegment(e.target.value as Segment)}
          >
            {(Object.keys(SEGMENT_LABEL) as Segment[]).map((s) => (
              <option key={s} value={s}>
                {SEGMENT_LABEL[s]}
              </option>
            ))}
          </select>
        </label>
      </div>
      {answer.error && answer.key === key ? (
        <p role="alert" className="text-sm">
          The figures could not be loaded.
        </p>
      ) : null}
      {data ? (
        <div className={`space-y-6 ${answer.key !== key ? "opacity-60" : ""}`}>
          <figure className="space-y-2">
            <figcaption className="font-medium text-ink">Median sale price</figcaption>
            <Legend name={name} />
            <MedianChart data={data} />
          </figure>
          <figure className="space-y-2">
            <figcaption className="font-medium text-ink">
              {periodKind === "rolling_12m"
                ? "Sales in the previous 12 months"
                : `Sales per ${PERIOD_LABEL[periodKind].toLowerCase()}`}
            </figcaption>
            <VolumeChart data={data} />
          </figure>
          <SeriesTable data={data} />
        </div>
      ) : !answer.error ? (
        <p aria-busy className="text-sm text-muted">
          Loading…
        </p>
      ) : null}
    </div>
  );
}

/** Share of sales per price band: the area's bars against Ireland's shares as ticks. */
export function PriceDistribution({ slug, name }: { slug: string; name: string }) {
  const [data, setData] = useState<Distribution | null>(null);
  const [error, setError] = useState(false);
  const [hover, setHover] = useState<number | null>(null);
  useEffect(() => {
    const request = new AbortController();
    api
      .areaDistribution(slug, { signal: request.signal })
      .then(setData)
      .catch(() => {
        if (!request.signal.aborted) setError(true);
      });
    return () => request.abort();
  }, [slug]);
  if (error) return <p className="text-sm">The price distribution could not be loaded.</p>;
  if (!data)
    return (
      <p aria-busy className="text-sm text-muted">
        Loading…
      </p>
    );
  if (data.n < 5)
    return (
      <p className="text-sm text-muted">
        Fewer than 5 market sales in {name} over these 12 months, so no distribution is shown.
      </p>
    );
  if (!data.bins.some((b) => (b.n ?? 0) >= 5))
    return (
      <p className="text-sm text-muted">
        {data.n.toLocaleString("en-IE")} market sales in {name} over these 12 months: too few in any
        one price band to show how they spread.
      </p>
    );
  const shares = data.bins.map((b) => (b.n != null ? b.n / data.n : null));
  const max = Math.max(
    ...shares.map((s) => s ?? 0),
    ...data.nationalShare.map((s) => s ?? 0),
    0.01,
  );
  const band = (i: number) => {
    const b = data.bins[i]!;
    return b.toEur == null
      ? `${formatEurShort(b.fromEur)}+`
      : `${formatEurShort(b.fromEur)}–${formatEurShort(b.toEur)}`;
  };
  const pct = (v: number) => `${(v * 100).toFixed(1)}%`;
  return (
    <figure className="space-y-3">
      <figcaption className="text-sm text-muted">
        Market sales from {formatMonth(data.windowStart)} to {formatMonth(data.windowEnd)} by price,
        as a share of all {data.n.toLocaleString("en-IE")} sales. Bands with fewer than 5 sales are
        not shown, and nor are enough others that they cannot be worked out from the total.
      </figcaption>
      <ul className="flex flex-wrap gap-x-4 text-xs text-ink-2">
        <li className="flex items-center gap-1.5">
          <span
            className="inline-block h-2.5 w-2.5 rounded-sm"
            style={{ background: AREA }}
            aria-hidden="true"
          />
          {name}
        </li>
        <li className="flex items-center gap-1.5">
          <span
            className="inline-block h-3 w-0.5"
            style={{ background: IRELAND }}
            aria-hidden="true"
          />
          Ireland
        </li>
      </ul>
      <ol className="space-y-1" onPointerLeave={() => setHover(null)}>
        {data.bins.map((b, i) => {
          const s = shares[i];
          const nat = data.nationalShare[i] ?? 0;
          return (
            <li
              key={b.fromEur}
              className="grid grid-cols-[5.5rem_1fr_4rem] items-center gap-2 text-xs"
              onPointerEnter={() => setHover(i)}
              tabIndex={0}
              onFocus={() => setHover(i)}
              aria-label={`${band(i)}: ${s != null ? `${b.n} sales, ${pct(s)}` : "not shown"}; Ireland ${pct(nat)}`}
            >
              <span className="text-right text-muted tabular-nums">{band(i)}</span>
              <span className="relative block h-3.5">
                {s != null && s > 0 ? (
                  <span
                    className="absolute inset-y-0 left-0 rounded-r-[4px]"
                    style={{
                      width: `${(s / max) * 100}%`,
                      background: AREA,
                      opacity: hover === i ? 0.8 : 1,
                    }}
                  />
                ) : null}
                <span
                  className="absolute -inset-y-0.5 w-0.5 rounded-full"
                  style={{
                    left: `calc(${(nat / max) * 100}% - 1px)`,
                    background: IRELAND,
                    boxShadow: "0 0 0 2px var(--color-surface)",
                  }}
                />
              </span>
              <span className="tabular-nums text-ink-2">{s != null ? pct(s) : "not shown"}</span>
            </li>
          );
        })}
      </ol>
      {hover !== null ? (
        <p className="text-xs text-ink-2" role="status">
          <strong className="text-ink">{band(hover)}</strong>:{" "}
          {data.bins[hover]!.n != null
            ? `${data.bins[hover]!.n} sales in ${name}`
            : "not shown (too few sales, or hidden with such a band)"}{" "}
          · Ireland {pct(data.nationalShare[hover] ?? 0)} of sales
        </p>
      ) : null}
    </figure>
  );
}
