import type { PriceEstimate } from "@/lib/api/client";
import { formatDate, formatEur, formatMonth } from "@/lib/format";

const BAND: Record<string, string> = {
  "0-3y": "less than 3 years apart",
  "3-7y": "3 to 7 years apart",
  "7y+": "7 or more years apart",
};

function signed(pct: number): string {
  return `${pct > 0 ? "+" : pct < 0 ? "−" : ""}${Math.abs(pct).toLocaleString("en-IE")}%`;
}

/**
 * What the CSO's price index implies the last market sale would fetch now (D-020, D-053): the
 * range first, because the single figure is only the index's guess, then how it was worked out.
 */
export function PriceEstimateCard({ estimate: e }: { estimate: PriceEstimate }) {
  if (!e.eligible || e.lowEur == null || e.highEur == null || e.midEur == null) {
    return (
      <p className="mt-2 text-sm text-muted">
        No index estimate for this home. {e.reason ?? "The price index is not loaded yet."}
      </p>
    );
  }
  const sale = e.basedOn;
  const cal = e.calibration;
  const series = e.series?.label ?? "its region";
  return (
    <>
      <p className="mt-3 text-sm font-medium text-ink-2">What the index implies, as a range</p>
      <p className="text-3xl font-semibold tracking-[-0.02em] text-ink tabular-nums sm:text-4xl">
        <span className="whitespace-nowrap">{formatEur(e.lowEur)} –</span>{" "}
        <span className="whitespace-nowrap">{formatEur(e.highEur)}</span>
      </p>
      <p className="mt-1 text-sm text-muted">Central figure {formatEur(e.midEur)}.</p>
      <dl className="mt-4 space-y-2 text-sm">
        {sale && e.indexMonth && e.indexChangePct != null ? (
          <div>
            <dt className="inline font-medium text-ink">Starting point: </dt>
            <dd className="inline text-ink-2">
              its last market sale, {formatEur(sale.priceEur)} on {formatDate(sale.date)}. The
              CSO&apos;s {series} index moved {signed(e.indexChangePct)} from that month to{" "}
              {formatMonth(e.indexMonth)}, the latest published.
            </dd>
          </div>
        ) : null}
        {cal ? (
          <div>
            <dt className="inline font-medium text-ink">Range: </dt>
            <dd className="inline text-ink-2">
              of {cal.pairs.toLocaleString("en-IE")} homes{" "}
              {cal.pooled ? "across Ireland" : `in the ${series} series`} that sold twice,{" "}
              {BAND[cal.yearsBetween]}, 8 in 10 sold for between {signed(cal.lowPct)} and{" "}
              {signed(cal.highPct)} of what this index implied (the middle one{" "}
              {signed(cal.medianPct)}).
              {cal.pooled
                ? " This region had too few such sales of its own, so Ireland's are used."
                : ""}
            </dd>
          </div>
        ) : null}
      </dl>
      <p className="mt-4 text-xs text-muted">{e.method}</p>
      <p className="mt-2 font-mono text-[0.7rem] text-muted">
        {e.series?.source ?? "CSO Residential Property Price Index (CC BY 4.0)"}
      </p>
    </>
  );
}
