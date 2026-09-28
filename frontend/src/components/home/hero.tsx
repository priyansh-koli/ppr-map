"use client";

import Link from "next/link";

import { ConfidenceChip } from "@/components/ui/confidence-chip";
import { Window } from "@/components/ui/window";
import type { PropertyListItem } from "@/lib/api/client";
import { formatDate, formatEur } from "@/lib/format";
import { ROUTES } from "@/lib/routes";

import { type Town, useLatestSales, useOverview } from "./data";

// Boxes around six town centres; each card shows the newest market sale inside its box.
const TOWNS: Town[] = [
  { name: "Dublin 8", bbox: "-6.300,53.328,-6.262,53.345" },
  { name: "Cork city", bbox: "-8.500,51.890,-8.440,51.910" },
  { name: "Galway city", bbox: "-9.080,53.265,-9.030,53.285" },
  { name: "Limerick city", bbox: "-8.650,52.655,-8.600,52.675" },
  { name: "Kilkenny", bbox: "-7.270,52.640,-7.230,52.665" },
  { name: "Sligo", bbox: "-8.490,54.265,-8.450,54.285" },
];

// Wide screens: cards float in two loose columns beside the headline. Below xl, a strip.
const SLOTS = [
  "xl:left-[1%] xl:top-[5%] xl:-rotate-3",
  "xl:left-[2.5%] xl:top-[38%] xl:rotate-2",
  "xl:left-[1%] xl:top-[71%] xl:-rotate-1",
  "xl:right-[1%] xl:top-[4%] xl:rotate-2",
  "xl:right-[2.5%] xl:top-[37%] xl:-rotate-2",
  "xl:right-[1%] xl:top-[70%] xl:rotate-3",
];

const fmt = new Intl.NumberFormat("en-IE");

function SaleCard({ town, item, slot }: { town: Town; item: PropertyListItem; slot: string }) {
  const sale = item.latestSale;
  return (
    <Link
      href={`/property/${item.id}`}
      className={`group relative block w-72 shrink-0 snap-start xl:w-60 transition-transform duration-300 ease-out-soft hover:z-10 hover:rotate-0 hover:scale-[1.03] xl:absolute ${slot}`}
    >
      <Window as="div" lift title={`latest sale · ${town.name}`} bodyClassName="px-4 pb-4 pt-3">
        <p className="truncate text-sm font-medium text-ink" title={item.address}>
          {item.address}
        </p>
        <p className="mt-1 font-display text-2xl font-bold tracking-tight text-ink">
          {formatEur(sale.priceEur)}
        </p>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-x-2 gap-y-1.5 text-xs text-muted">
          <span className="whitespace-nowrap">
            {sale.isNew ? "New" : "Second-hand"} · {formatDate(sale.date)}
          </span>
          <ConfidenceChip confidence={item.confidence} />
        </div>
      </Window>
    </Link>
  );
}

export function Hero() {
  const { data } = useOverview();
  const sales = useLatestSales(TOWNS);
  const dublin = data?.counties.find((c) => c.slug === "dublin");

  return (
    <section className="relative mx-auto max-w-7xl px-4 pb-10 pt-12 sm:pt-16 xl:min-h-[720px] xl:pt-24">
      <div className="relative z-[5] mx-auto max-w-3xl text-center xl:max-w-xl">
        <p className="eyebrow">Property Price Register · every county · since 2010</p>
        <h1 className="mt-4 font-display text-5xl font-extrabold leading-[0.95] tracking-[-0.035em] text-ink sm:text-7xl xl:text-[5.2rem]">
          Every home sold in Ireland, <span className="marker">on one map.</span>
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg text-ink-2 sm:text-xl">
          {data ? (
            <>
              <strong className="font-semibold text-ink">
                {fmt.format(data.totalSales)} sales
              </strong>{" "}
              from the register since {new Date(data.firstSaleDate).getUTCFullYear()}
            </>
          ) : (
            "Every sale on the register since 2010"
          )}
          , each placed as precisely as its address allows, and each one telling you how precise
          that is.
        </p>
        <div className="mt-8 flex flex-col items-stretch justify-center gap-3 sm:flex-row sm:items-center">
          <Link href={ROUTES.map.path} className="btn btn-primary px-6 text-base">
            Open the map
            <svg viewBox="0 0 16 16" className="h-4 w-4" aria-hidden="true">
              <path
                d="M3 8h9M8.5 4.5 12 8l-3.5 3.5"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </Link>
          <a href="#counties" className="btn btn-secondary px-6 text-base">
            Prices by county
          </a>
        </div>
      </div>

      {/* Stickers: real figures only, and only once they have loaded. */}
      {data ? (
        <p
          aria-hidden="true"
          className="pointer-events-none absolute left-[25%] top-[80%] z-[6] hidden -rotate-6 bg-[#ffe27a] px-4 py-3 font-hand text-2xl leading-tight text-[#2b2410] shadow-window xl:block"
        >
          {fmt.format(data.totalSales)} sales.
          <br />
          {fmt.format(data.totalProperties)} homes.
          <br />
          one map.
        </p>
      ) : null}
      {dublin?.medianPriceEur ? (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute right-[24%] top-[78%] z-[6] hidden rotate-[5deg] xl:block"
        >
          <div className="rounded-md bg-sign px-5 pb-1 pt-2 text-center font-display text-3xl font-extrabold tracking-[0.2em] text-white shadow-window">
            SOLD
          </div>
          <div className="mx-auto -mt-0.5 w-44 rounded-b-md bg-surface px-3 py-2 text-center shadow-window">
            <p className="text-[0.65rem] font-semibold uppercase tracking-wider text-muted">
              Dublin median, 12 months
            </p>
            <p className="font-display text-xl font-bold text-ink">
              {formatEur(dublin.medianPriceEur)}
            </p>
          </div>
        </div>
      ) : null}

      {sales && sales.some(Boolean) ? (
        <div className="relative mt-12 xl:absolute xl:inset-0 xl:mt-0">
          <h2 className="sr-only">Latest sales in six towns</h2>
          <ul className="-mx-4 flex snap-x gap-4 overflow-x-auto px-4 pb-6 pt-2 xl:contents">
            {TOWNS.map((town, i) => {
              const item = sales[i];
              return item ? (
                <li key={town.name} className="xl:contents">
                  <SaleCard town={town} item={item} slot={SLOTS[i] ?? ""} />
                </li>
              ) : null;
            })}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
