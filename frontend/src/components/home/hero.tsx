"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { PlaceSearch } from "@/components/search/place-search";
import { ConfidenceChip } from "@/components/ui/confidence-chip";
import { Contours } from "@/components/ui/contours";
import { Window } from "@/components/ui/window";
import { DEFAULT_FILTERS, filtersToParams } from "@/lib/filters";
import { formatDate, formatEur } from "@/lib/format";
import { withSuggestion } from "@/lib/search";
import { ROUTES } from "@/lib/routes";

import { type Town, useLatestSales, useOverview } from "./data";

// Boxes around six town centres; each row shows the newest market sale inside its box.
const TOWNS: Town[] = [
  { name: "Dublin 8", bbox: "-6.300,53.328,-6.262,53.345" },
  { name: "Cork city", bbox: "-8.500,51.890,-8.440,51.910" },
  { name: "Galway city", bbox: "-9.080,53.265,-9.030,53.285" },
  { name: "Limerick city", bbox: "-8.650,52.655,-8.600,52.675" },
  { name: "Kilkenny", bbox: "-7.270,52.640,-7.230,52.665" },
  { name: "Sligo", bbox: "-8.490,54.265,-8.450,54.285" },
];

const fmt = new Intl.NumberFormat("en-IE");

/** A register's ink stamp with the real totals, once they have loaded. */
function RegisterStamp({ sales, since }: { sales: number; since: number }) {
  const ring = `PROPERTY PRICE REGISTER · EVERY SALE SINCE ${since} · `;
  return (
    <svg viewBox="0 0 160 160" className="h-36 w-36 -rotate-12 text-accent" aria-hidden="true">
      <defs>
        <path id="stamp-ring" d="M80 80m-60 0a60 60 0 1 1 120 0a60 60 0 1 1-120 0" />
      </defs>
      <circle cx="80" cy="80" r="76" fill="none" stroke="currentColor" strokeWidth="2.5" />
      <circle cx="80" cy="80" r="46" fill="none" stroke="currentColor" strokeWidth="1.2" />
      <text fill="currentColor" className="font-mono" fontSize="10.5" letterSpacing="1.6">
        <textPath href="#stamp-ring">{ring}</textPath>
      </text>
      <text
        x="80"
        y="80"
        textAnchor="middle"
        fill="currentColor"
        className="font-sans"
        fontSize="19"
        fontWeight="700"
      >
        {fmt.format(sales)}
      </text>
      <text
        x="80"
        y="97"
        textAnchor="middle"
        fill="currentColor"
        className="font-mono"
        fontSize="10"
      >
        SALES
      </text>
    </svg>
  );
}

function Ledger() {
  const sales = useLatestSales(TOWNS);
  return (
    <Window as="div" lift title="register · latest entries" bodyClassName="p-0">
      <h2 className="sr-only">The latest sale in six towns</h2>
      <ol className="divide-y divide-line">
        {TOWNS.map((town, i) => {
          const item = sales?.[i];
          if (sales && !item) return null;
          return (
            <li key={town.name}>
              {item ? (
                <Link
                  href={`/property/${item.id}`}
                  className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1 px-5 py-3.5 hover:bg-surface-2"
                >
                  <span className="min-w-0">
                    <span className="eyebrow block">{town.name}</span>
                    <span className="block truncate font-medium text-ink" title={item.address}>
                      {item.address}
                    </span>
                  </span>
                  <span className="text-right text-lg font-semibold text-ink tabular-nums">
                    {formatEur(item.latestSale.priceEur)}
                  </span>
                  <span className="text-xs text-muted">
                    {item.latestSale.isNew ? "New" : "Second-hand"} ·{" "}
                    {formatDate(item.latestSale.date)}
                  </span>
                  <span className="justify-self-end">
                    <ConfidenceChip confidence={item.confidence} />
                  </span>
                </Link>
              ) : (
                <div aria-hidden="true" className="px-5 py-4">
                  <div className="h-3 w-20 rounded bg-fill" />
                  <div className="mt-2 h-4 w-3/4 rounded bg-fill" />
                </div>
              )}
            </li>
          );
        })}
      </ol>
      <p className="border-t border-line px-5 py-3 text-xs text-muted">
        The newest market sale filed in each town. Open one for its full history.
      </p>
    </Window>
  );
}

/** The hero's search bar: a place opens its search, an address opens the property. */
function HeroSearch() {
  const router = useRouter();
  return (
    <div className="mt-8 max-w-xl">
      <PlaceSearch
        size="lg"
        label="Search a town, area, Eircode routing key or address"
        onSelect={(s) => {
          const f = withSuggestion(DEFAULT_FILTERS, s);
          if (f) router.push(`${ROUTES.search.path}?${filtersToParams(f).toString()}`);
          else if (s.propertyId) router.push(`/property/${s.propertyId}`);
        }}
      />
    </div>
  );
}

export function Hero() {
  const { data } = useOverview();
  return (
    <section className="relative isolate overflow-hidden">
      <Contours className="-z-10" />
      <div className="mx-auto grid max-w-7xl items-center gap-12 px-4 pb-16 pt-12 sm:pt-20 lg:grid-cols-[1.15fr_1fr] lg:gap-16 lg:pb-24">
        <div>
          <p className="eyebrow">Property Price Register · every county · since 2010</p>
          <h1 className="mt-5 font-display text-5xl font-semibold leading-[1.02] tracking-[-0.015em] text-ink sm:text-6xl xl:text-7xl">
            Ireland&rsquo;s home sales, <span className="hl">on the record.</span>
          </h1>
          <p className="mt-6 max-w-xl text-lg text-ink-2 sm:text-xl">
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
          <HeroSearch />
          <div className="mt-4 flex flex-col gap-3 sm:flex-row">
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
        <div className="relative">
          {data ? (
            <div className="absolute -bottom-16 -left-44 z-10 hidden opacity-90 xl:block">
              <RegisterStamp
                sales={data.totalSales}
                since={new Date(data.firstSaleDate).getUTCFullYear()}
              />
            </div>
          ) : null}
          <Ledger />
        </div>
      </div>
    </section>
  );
}
