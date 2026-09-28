"use client";

import { useState } from "react";

import { Window } from "@/components/ui/window";
import { formatDate, formatMonth } from "@/lib/format";

import { useOverview } from "./data";

const fmt = new Intl.NumberFormat("en-IE");
const monthShort = new Intl.DateTimeFormat("en-IE", { month: "short", timeZone: "UTC" });

/**
 * Sales filed per month, nationally, for 24 months. One series, so no legend: the title says
 * what it is. The provisional months are a lighter step of the same hue, and labelled, since
 * late filings still arrive for them (ARCHITECTURE.md). A table view carries every value.
 */
export function MonthlyChart() {
  const { data, failed } = useOverview();
  const [hover, setHover] = useState<number | null>(null);

  const months = data?.monthly ?? [];
  const first = months[0];
  const last = months[months.length - 1];
  if (!data || !first || !last) {
    return (
      <Window title="register · sales per month" bodyClassName="p-6">
        <p className="py-16 text-center text-muted">
          {failed
            ? "The chart needs the data server, which is not available right now."
            : "Loading…"}
        </p>
      </Window>
    );
  }

  const max = Math.max(...months.map((m) => m.sales));
  const complete = months.filter((m) => !m.provisional);
  const last12 = complete.slice(-12).reduce((sum, m) => sum + m.sales, 0);
  const busiest = complete.reduce((a, b) => (b.sales > a.sales ? b : a), complete[0] ?? first);
  const firstProvisional = months.find((m) => m.provisional);
  const shown = hover === null ? null : months[hover];

  return (
    <Window title="register · sales per month" bodyClassName="p-5 sm:p-7">
      <div className="flex flex-wrap items-start justify-between gap-x-10 gap-y-3">
        <div>
          <p className="text-sm font-medium text-ink-2">
            Market sales in the last 12 complete months
          </p>
          <p className="font-display text-5xl font-extrabold tracking-[-0.03em] text-ink sm:text-6xl">
            {fmt.format(last12)}
          </p>
        </div>
        <p className="max-w-sm text-sm text-muted">
          Busiest month: <strong className="text-ink">{formatMonth(busiest.month)}</strong>,{" "}
          {fmt.format(busiest.sales)} sales.
          {firstProvisional ? (
            <>
              {" "}
              Months from {formatMonth(firstProvisional.month)} are provisional: sales are filed
              weeks after they close, so these bars still grow.
            </>
          ) : null}
        </p>
      </div>

      <div className="relative mt-6" onMouseLeave={() => setHover(null)}>
        <p
          aria-hidden="true"
          className={`pointer-events-none absolute -top-2 left-0 rounded-md bg-ink px-2 py-1 text-xs font-medium text-desk shadow-window transition-opacity ${
            shown ? "opacity-100" : "opacity-0"
          }`}
        >
          {shown
            ? `${formatMonth(shown.month)}: ${fmt.format(shown.sales)} sales${shown.provisional ? " so far (provisional)" : ""}`
            : " "}
        </p>
        <div aria-hidden="true" className="flex h-44 items-end gap-[2px] pt-8 sm:h-56">
          {months.map((m, i) => (
            <div
              key={m.month}
              onMouseEnter={() => setHover(i)}
              className="flex h-full flex-1 items-end justify-center"
            >
              <div
                className={`w-full max-w-6 rounded-t-[4px] transition-opacity ${
                  m.provisional ? "bg-accent/35" : "bg-accent"
                } ${hover !== null && hover !== i ? "opacity-60" : ""}`}
                style={{ height: `${Math.max((m.sales / max) * 100, 1)}%` }}
              />
            </div>
          ))}
        </div>
        <div
          aria-hidden="true"
          className="mt-2 flex justify-between border-t border-line pt-2 font-mono text-xs text-muted"
        >
          <span>{formatMonth(first.month)}</span>
          {firstProvisional ? <span>provisional →</span> : null}
          <span>{monthShort.format(new Date(`${last.month}T00:00:00Z`))} so far</span>
        </div>
      </div>

      <details className="mt-4 text-sm">
        <summary className="cursor-pointer font-medium text-accent">Show as a table</summary>
        <div className="mt-3 max-h-72 overflow-auto rounded-[10px] border border-line">
          <table className="w-full text-left">
            <caption className="sr-only">
              Market sales per month, all counties, register data up to{" "}
              {formatDate(data.dataVersion.slice(0, 10))}
            </caption>
            <thead className="sticky top-0 bg-surface-2 text-muted">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">
                  Month
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Sales
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Status
                </th>
              </tr>
            </thead>
            <tbody>
              {[...months].reverse().map((m) => (
                <tr key={m.month} className="border-t border-line">
                  <th scope="row" className="px-3 py-1.5 font-normal text-ink">
                    {formatMonth(m.month)}
                  </th>
                  <td className="px-3 py-1.5 text-right text-ink">{fmt.format(m.sales)}</td>
                  <td className="px-3 py-1.5 text-muted">
                    {m.provisional ? "Provisional" : "Complete"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </Window>
  );
}
