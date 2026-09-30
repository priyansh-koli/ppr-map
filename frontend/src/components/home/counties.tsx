"use client";

import Link from "next/link";

import { formatEur, formatMonth } from "@/lib/format";

import { useOverview } from "./data";

/** The county index marks on Irish number plates (D, C, G…), a shape everyone here knows. */
const PLATE: Record<string, string> = {
  carlow: "CW",
  cavan: "CN",
  clare: "CE",
  cork: "C",
  donegal: "DL",
  dublin: "D",
  galway: "G",
  kerry: "KY",
  kildare: "KE",
  kilkenny: "KK",
  laois: "LS",
  leitrim: "LM",
  limerick: "L",
  longford: "LD",
  louth: "LH",
  mayo: "MO",
  meath: "MH",
  monaghan: "MN",
  offaly: "OY",
  roscommon: "RN",
  sligo: "SO",
  tipperary: "T",
  waterford: "W",
  westmeath: "WH",
  wexford: "WX",
  wicklow: "WW",
};

const count = new Intl.NumberFormat("en-IE", { notation: "compact", maximumFractionDigits: 1 });
// €414K rather than €414.1K: three figures are plenty for a median on a tile.
const median = new Intl.NumberFormat("en-IE", {
  style: "currency",
  currency: "EUR",
  notation: "compact",
  maximumSignificantDigits: 3,
});

export function Counties() {
  const { data, failed } = useOverview();
  const period = data ? `${formatMonth(data.windowStart)} to ${formatMonth(data.windowEnd)}` : null;

  return (
    <section
      id="counties"
      aria-labelledby="counties-heading"
      className="mx-auto max-w-7xl scroll-mt-20 px-4 py-16"
    >
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2
            id="counties-heading"
            className="font-display text-4xl font-semibold tracking-[-0.015em] text-ink sm:text-5xl"
          >
            Twenty-six counties. <span className="hl">One register.</span>
          </h2>
          <p className="mt-3 max-w-2xl text-lg text-ink-2">
            Market sales and the median price in each county over the latest complete 12 months
            {period ? `, ${period}` : ""}. Open a county for its prices over time, its towns and its
            sales on the map.
          </p>
        </div>
        <p className="eyebrow">sorted by sales, most first</p>
      </div>

      {data ? (
        <ul className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
          {data.counties.map((c) => (
            <li key={c.slug}>
              <Link
                href={`/area/${c.slug}`}
                className="group relative flex h-full flex-col rounded-[14px] bg-surface p-3 shadow-window outline outline-1 -outline-offset-1 outline-line transition-transform duration-200 ease-out-soft hover:-translate-y-0.5 hover:shadow-lift"
              >
                <span className="flex items-center gap-2.5">
                  <span
                    aria-hidden="true"
                    className="flex h-8 min-w-11 items-center justify-center rounded-[5px] border-2 border-ink bg-white px-1.5 font-mono text-[0.8rem] font-semibold tracking-wider text-[#111]"
                  >
                    {PLATE[c.slug] ?? c.name.slice(0, 2).toUpperCase()}
                  </span>
                  <span className="font-display text-lg font-semibold leading-tight text-ink">
                    {c.name}
                  </span>
                </span>
                <span className="mt-3 grid grid-cols-2 gap-2 border-t border-line pt-2.5 text-sm">
                  <span>
                    <span className="block text-xs text-muted">sales</span>
                    <span className="font-semibold text-ink tabular-nums">
                      {count.format(c.sales)}
                    </span>
                  </span>
                  <span>
                    <span className="block text-xs text-muted">median</span>
                    {c.medianPriceEur ? (
                      <span
                        className="font-semibold text-ink tabular-nums"
                        title={formatEur(c.medianPriceEur)}
                      >
                        {median.format(c.medianPriceEur)}
                      </span>
                    ) : (
                      <span className="text-muted">too few sales</span>
                    )}
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-8 rounded-[14px] border border-dashed border-line-strong px-4 py-10 text-center text-muted">
          {failed
            ? "County figures need the data server, which is not available right now."
            : "Loading county figures…"}
        </p>
      )}
    </section>
  );
}
