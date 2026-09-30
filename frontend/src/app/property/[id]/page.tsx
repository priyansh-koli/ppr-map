import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { RecordView } from "@/components/auth/record-view";
import { SaveButton } from "@/components/auth/save-button";
import { PlaceholderPage, pageMetadata } from "@/components/placeholder-page";
import { AreaTrend } from "@/components/property/area-trend";
import { ConfidenceChip } from "@/components/ui/confidence-chip";
import { PageHeader } from "@/components/ui/page-header";
import { Window } from "@/components/ui/window";
import { api, ApiError, type PropertyDetail, STATIC_PREVIEW } from "@/lib/api/client";
import {
  CONFIDENCE_LABEL,
  CONFIDENCE_NOTE,
  formatDate,
  formatDistance,
  formatEur,
  formatRate,
} from "@/lib/format";
import { ROUTES } from "@/lib/routes";

type Props = { params: Promise<{ id: string }> };

// The static export (D-034) needs every path at build time; it only has the sample URL from
// `routes.ts` and shows the placeholder. The server build renders any id on request.
export function generateStaticParams() {
  return [{ id: "example" }];
}

async function load(id: string): Promise<PropertyDetail | "unavailable" | null> {
  try {
    return await api.property(id, { cache: "no-store" });
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    return "unavailable";
  }
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  if (STATIC_PREVIEW) return pageMetadata("property");
  const data = await load((await params).id);
  return data && data !== "unavailable"
    ? { title: data.address, description: `Sale history for ${data.address}.` }
    : pageMetadata("property");
}

const KIND_LABEL: Record<string, string> = {
  small_area: "Small Area",
  electoral_division: "Electoral Division",
  townland: "Townland",
  settlement: "Town or city",
  county: "County",
};

function SaleFlags({ sale }: { sale: PropertyDetail["sales"][number] }) {
  const flags = [
    sale.isNew ? "New build" : "Second-hand",
    sale.vatExclusive ? "price excludes VAT" : null,
    sale.notFullMarketPrice ? "not full market price" : null,
    sale.bulkGroupSize ? `bulk sale of ${sale.bulkGroupSize}` : null,
    sale.possibleDuplicate ? "possible repeat filing" : null,
  ].filter(Boolean);
  return (
    <>
      {flags.join(", ")}
      {sale.vatEstimates?.length ? (
        <span className="mt-0.5 block text-ink-2">
          {sale.vatEstimates
            .map((e) =>
              e.appliesTo === "qualifying_apartment"
                ? `≈ ${formatEur(e.priceEur)} if a qualifying apartment (${formatRate(e.rate)})`
                : `≈ ${formatEur(e.priceEur)} with VAT at ${formatRate(e.rate)} (estimate)`,
            )
            .join("; ")}
        </span>
      ) : null}
    </>
  );
}

const pct = new Intl.NumberFormat("en-IE", {
  style: "percent",
  maximumFractionDigits: 0,
  signDisplay: "exceptZero",
});

type SaleRow = PropertyDetail["sales"][number];

/** Change against the previous sale, only between two plain market sales. */
function changeSince(sale: SaleRow, previous: SaleRow | undefined): string | null {
  const plain = (s: SaleRow) =>
    !s.vatExclusive && !s.notFullMarketPrice && !s.bulkGroupSize && !s.possibleDuplicate;
  if (!previous || !plain(sale) || !plain(previous)) return null;
  const before = Number(previous.priceEur);
  return before > 0 ? pct.format(Number(sale.priceEur) / before - 1) : null;
}

function Sourced({
  label,
  value,
  source,
  asOf,
}: {
  label: string;
  value: string;
  source: string;
  asOf?: string | null;
}) {
  return (
    <div className="rounded-[10px] bg-surface-2 px-4 py-3">
      <dt className="text-muted">{label}</dt>
      <dd className="mt-0.5 font-medium text-ink">
        {value}
        <span className="mt-1 block font-mono text-[0.7rem] font-normal text-muted">
          {source}
          {asOf ? `, ${asOf}` : ""}
        </span>
      </dd>
    </div>
  );
}

export default async function Page({ params }: Props) {
  const { id } = await params;
  if (STATIC_PREVIEW) return <PlaceholderPage routeKey="property" detail={`ID: ${id}`} />;
  const data = await load(id);
  if (data === null) notFound();
  if (data === "unavailable") {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12">
        <PageHeader title={ROUTES.property.title} />
        <p className="mt-4 text-muted">
          This property could not be loaded right now. Please try again shortly.
        </p>
      </div>
    );
  }
  const v = data.vicinity;
  const loc = data.location;
  const county = data.county.charAt(0).toUpperCase() + data.county.slice(1);
  const latest = data.sales[0];
  const hasNearby = Boolean(
    v.nearestStop || v.nearestPrimarySchool || v.shopsWithin1km || v.deprivation,
  );
  return (
    <article className="mx-auto max-w-4xl space-y-6 px-4 py-12">
      <header>
        <p className="eyebrow">
          register · county {county}
          {data.routingKey ? ` · Eircode area ${data.routingKey}` : ""}
        </p>
        <h1 className="mt-2 font-display text-4xl font-semibold leading-[1.02] tracking-[-0.015em] text-ink sm:text-5xl">
          {data.address}
        </h1>
        <RecordView propertyId={data.id} />
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <ConfidenceChip confidence={loc.confidence} />
          <Link
            className="btn btn-secondary btn-sm"
            href={`${ROUTES.map.path}?lat=${loc.lat.toFixed(5)}&lng=${loc.lng.toFixed(5)}&z=${loc.confidence === "exact" || loc.confidence === "street" ? 17 : 14}`}
          >
            Show on the map
          </Link>
          <SaveButton propertyId={data.id} />
        </div>
        <p className="mt-3 text-sm">
          <span className="font-medium text-ink">
            Location: {CONFIDENCE_LABEL[loc.confidence]}.
          </span>{" "}
          <span className="text-muted">{CONFIDENCE_NOTE[loc.confidence]}</span>
        </p>
      </header>

      <Window
        title={`register · ${data.sales.length} ${data.sales.length === 1 ? "sale" : "sales"}`}
        labelledBy="sales-heading"
        bodyClassName="p-5 sm:p-7"
      >
        <h2 id="sales-heading" className="sr-only">
          Sales
        </h2>
        {latest ? (
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-ink-2">
                Latest sale, {formatDate(latest.date)}
              </p>
              <p className="text-5xl font-semibold tracking-[-0.02em] text-ink tabular-nums">
                {formatEur(latest.priceEur)}
              </p>
            </div>
          </div>
        ) : null}
        <div className="mt-5 overflow-x-auto">
          <table className="w-full min-w-[28rem] text-left text-sm">
            <caption className="sr-only">Every sale of this property on the register</caption>
            <thead>
              <tr className="text-muted">
                <th scope="col" className="py-2 pr-4 font-medium">
                  Date
                </th>
                <th scope="col" className="py-2 pr-4 text-right font-medium">
                  Price
                </th>
                <th scope="col" className="py-2 pr-4 text-right font-medium">
                  Change
                </th>
                <th scope="col" className="py-2 font-medium">
                  Details
                </th>
              </tr>
            </thead>
            <tbody>
              {/* Repeat filings share a date and price, so the row's position is part of its key. */}
              {data.sales.map((sale, i) => {
                const change = changeSince(sale, data.sales[i + 1]);
                return (
                  <tr
                    key={`${i}-${sale.date}-${sale.priceEur}`}
                    className="border-t border-line align-top"
                  >
                    <td className="py-2.5 pr-4">{formatDate(sale.date)}</td>
                    <td className="py-2.5 pr-4 text-right font-semibold text-ink">
                      {formatEur(sale.priceEur)}
                    </td>
                    <td className="py-2.5 pr-4 text-right text-ink-2">{change ?? "–"}</td>
                    <td className="py-2.5 text-muted">
                      <SaleFlags sale={sale} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {data.sales.length > 1 ? (
          <p className="mt-3 text-xs text-muted">
            Change is against the sale below it, in the prices as filed: not adjusted for inflation
            or for work done. It is left out where either sale is not a plain market sale.
          </p>
        ) : null}
      </Window>

      {data.caveats.length ? (
        <section
          aria-labelledby="caveats-heading"
          className="rounded-[14px] bg-accent-wash p-5 text-sm text-ink shadow-window"
        >
          <h2 id="caveats-heading" className="font-display text-xl font-semibold">
            Worth knowing
          </h2>
          <ul className="mt-3 list-disc space-y-1 pl-5">
            {data.caveats.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <Window
        title="nearby · with sources"
        labelledBy="vicinity-heading"
        bodyClassName="p-5 sm:p-7"
      >
        <h2 id="vicinity-heading" className="font-display text-2xl font-bold text-ink">
          Nearby
        </h2>
        {hasNearby ? (
          <>
            <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
              {v.nearestStop ? (
                <Sourced
                  label="Nearest public transport stop"
                  value={`${v.nearestStop.value.name ?? "Unnamed stop"}, ${formatDistance(v.nearestStop.value.distanceM)}`}
                  source={v.nearestStop.source}
                  asOf={v.nearestStop.asOf}
                />
              ) : null}
              {v.nearestPrimarySchool ? (
                <Sourced
                  label="Nearest primary school"
                  value={`${v.nearestPrimarySchool.value.name ?? "Unnamed school"}, ${formatDistance(v.nearestPrimarySchool.value.distanceM)}`}
                  source={v.nearestPrimarySchool.source}
                  asOf={v.nearestPrimarySchool.asOf}
                />
              ) : null}
              {v.nearestPostPrimarySchool ? (
                <Sourced
                  label="Nearest post-primary school"
                  value={`${v.nearestPostPrimarySchool.value.name ?? "Unnamed school"}, ${formatDistance(v.nearestPostPrimarySchool.value.distanceM)}`}
                  source={v.nearestPostPrimarySchool.source}
                  asOf={v.nearestPostPrimarySchool.asOf}
                />
              ) : null}
              {v.shopsWithin1km ? (
                <Sourced
                  label="Shops within 1 km"
                  value={String(v.shopsWithin1km.value)}
                  source={v.shopsWithin1km.source}
                  asOf={v.shopsWithin1km.asOf}
                />
              ) : null}
              {v.deprivation ? (
                <Sourced
                  label="Area deprivation index"
                  value={v.deprivation.value}
                  source={v.deprivation.source}
                  asOf={v.deprivation.asOf}
                />
              ) : null}
            </dl>
            <p className="mt-4 text-xs text-muted">
              Distances are straight lines, not walking routes. Schools come from OpenStreetMap and
              may be incomplete.
            </p>
          </>
        ) : (
          <p className="mt-2 text-sm text-muted">
            Nearby places are only shown when the address itself or its street was found.
          </p>
        )}
        <p className="mt-4 text-sm">
          Flood risk:{" "}
          <a className="prose-link" href={v.flood.link}>
            {v.flood.note}
          </a>
          .
        </p>
      </Window>

      {data.areaSeries ? (
        <Window title="area · median price" labelledBy="trend-heading" bodyClassName="p-5 sm:p-7">
          <h2 id="trend-heading" className="font-display text-2xl font-bold text-ink">
            Prices in {data.areaSeries.area.name}
          </h2>
          <div className="mt-4">
            <AreaTrend series={data.areaSeries} />
          </div>
        </Window>
      ) : null}

      <Window
        title="areas · this address is in"
        labelledBy="areas-heading"
        bodyClassName="p-5 sm:p-7"
      >
        <h2 id="areas-heading" className="sr-only">
          Areas
        </h2>
        <ul className="grid gap-2 text-sm sm:grid-cols-2">
          {data.areas.map((a) => (
            <li key={`${a.kind}-${a.slug}`}>
              <Link
                href={`/area/${a.slug}`}
                className="block rounded-[10px] bg-surface-2 px-3 py-2 hover:bg-fill"
              >
                <span className="block text-xs text-muted">{KIND_LABEL[a.kind] ?? a.kind}</span>
                <span className="text-ink underline decoration-line underline-offset-2">
                  {a.kind === "small_area" ? `Small Area ${a.name}` : a.name}
                </span>
              </Link>
            </li>
          ))}
        </ul>
        <p className="mt-4 font-mono text-xs text-muted">data version {data.dataVersion}</p>
      </Window>
    </article>
  );
}
